from __future__ import annotations

import html
import io
import re
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE = "https://sei.ivc.br"
LOGIN_URL = f"{BASE}/index.xhtml"
HOME_URL = f"{BASE}/visaoAdministrativo/administrativo/homeAdministrador.xhtml"
REPORT_URL = (
    f"{BASE}/visaoAdministrativo/avaliacaoInstitucional/relatorio/"
    "avaliacaoInstitucionalRel.xhtml"
)
KNOWLEDGE_URL = f"{BASE}/webservice/baseconhecimento/ativos"


@dataclass
class EvaluationSearchResult:
    name: str
    source: str
    start_date: str | None = None
    end_date: str | None = None
    target: str | None = None
    status: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class QuestionnaireOption:
    sei_id: str
    name: str
    selected: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ReportFilterOption:
    value: str
    label: str
    selected: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class EvaluationMetadata:
    evaluation_name: str | None
    start_date: str | None
    end_date: str | None
    target: str | None = None
    status: str | None = None
    questionnaires: list[QuestionnaireOption] = field(default_factory=list)
    selected_questionnaire_id: str | None = None
    selected_questionnaire_name: str | None = None
    question_count: int = 0
    detail_field_name: str | None = None
    detail_value: str = "AVALIADO"
    detail_options: list[ReportFilterOption] = field(default_factory=list)
    unit_value: str = "2"
    unit_options: list[ReportFilterOption] = field(default_factory=list)
    turn_value: str = "0"
    turn_options: list[ReportFilterOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "evaluation_name": self.evaluation_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "target": self.target,
            "status": self.status,
            "questionnaires": [item.to_dict() for item in self.questionnaires],
            "selected_questionnaire_id": self.selected_questionnaire_id,
            "selected_questionnaire_name": self.selected_questionnaire_name,
            "question_count": self.question_count,
            "detail_value": self.detail_value,
            "detail_options": [item.to_dict() for item in self.detail_options],
            "unit_value": self.unit_value,
            "unit_options": [item.to_dict() for item in self.unit_options],
            "turn_value": self.turn_value,
            "turn_options": [item.to_dict() for item in self.turn_options],
        }


@dataclass
class DownloadedReport:
    filename: str
    content: bytes
    kind: str
    content_type: str | None
    download_path: str
    progress: dict | None = None


class SEIConnectorError(RuntimeError):
    pass


class SEIInstitutionalEvaluationConnector:
    """Cliente HTTP do relatório de Avaliação Institucional do SEI.

    O conector preserva uma única requests.Session, atualiza o ViewState após
    cada resposta JSF/RichFaces e executa as ações de forma sequencial. Isso é
    intencional: chamadas concorrentes sobre a mesma sessão podem corromper o
    estado do backing bean do JSF.
    """

    def __init__(self, *, request_timeout: int = 60) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) "
                    "Gecko/20100101 Firefox/152.0"
                ),
                "Accept-Language": "pt-BR,en-US;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
            }
        )
        self.request_timeout = request_timeout
        self.viewstate: str | None = None
        self.logged_in = False
        self.report_open = False
        self.last_search_results: dict[str, EvaluationSearchResult] = {}
        self.last_search_form_values: dict[str, str] = {}
        self.report_main_values: dict[str, str] = {}
        self.report_page_text: str = ""
        self.metadata: EvaluationMetadata | None = None
        self.last_progress: dict | None = None
        self.lock = threading.RLock()

    # -------------------------- JSF helpers --------------------------

    @staticmethod
    def _extract_viewstate(text: str) -> str | None:
        soup = BeautifulSoup(text, "html.parser")
        field = soup.find("input", attrs={"name": "javax.faces.ViewState"})
        if field and field.get("value"):
            return html.unescape(str(field["value"]))

        match = re.search(
            r'<update[^>]+id=["\'][^"\']*javax\.faces\.ViewState[^"\']*["\'][^>]*>'
            r'\s*<!\[CDATA\[(.*?)\]\]>\s*</update>',
            text,
            flags=re.I | re.S,
        )
        return html.unescape(match.group(1).strip()) if match else None

    def _update_viewstate(self, response: requests.Response) -> None:
        value = self._extract_viewstate(response.text)
        if value:
            self.viewstate = value

    @staticmethod
    def _click_payload(form: str, source: str, values: dict[str, str] | None = None) -> dict[str, str]:
        data = dict(values or {})
        data.setdefault(form, form)
        data.update(
            {
                "javax.faces.source": source,
                "javax.faces.partial.event": "click",
                "javax.faces.partial.execute": f"{source} @component",
                "javax.faces.partial.render": "@component",
                "org.richfaces.ajax.component": source,
                source: source,
                "rfExt": "null",
                "AJAX:EVENTS_COUNT": "1",
                "javax.faces.partial.ajax": "true",
            }
        )
        return data

    @staticmethod
    def _change_payload(form: str, source: str, values: dict[str, str]) -> dict[str, str]:
        data = dict(values)
        data.setdefault(form, form)
        data.update(
            {
                "javax.faces.source": source,
                "javax.faces.partial.event": "change",
                "javax.faces.partial.execute": f"{source} @component",
                "javax.faces.partial.render": "@component",
                "javax.faces.behavior.event": "change",
                "org.richfaces.ajax.component": source,
                "rfExt": "null",
                "AJAX:EVENTS_COUNT": "1",
                "javax.faces.partial.ajax": "true",
            }
        )
        return data

    @staticmethod
    def _component_payload(form: str, source: str) -> dict[str, str]:
        # Poll/encerrar/oncomplete2 não enviam javax.faces.partial.event=click
        # no HAR; reproduzimos exatamente essa forma mais simples.
        return {
            form: form,
            "javax.faces.source": source,
            "javax.faces.partial.execute": f"{source} @component",
            "javax.faces.partial.render": "@component",
            "org.richfaces.ajax.component": source,
            source: source,
            "rfExt": "null",
            "AJAX:EVENTS_COUNT": "1",
            "javax.faces.partial.ajax": "true",
        }

    def _ajax_post(self, url: str, data: dict[str, str], *, referer: str) -> requests.Response:
        if not self.viewstate:
            raise SEIConnectorError("O SEI não forneceu javax.faces.ViewState.")

        payload = dict(data)
        payload["javax.faces.ViewState"] = self.viewstate
        response = self.session.post(
            url,
            headers={
                "Accept": "*/*",
                "Faces-Request": "partial/ajax",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": BASE,
                "Referer": referer,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            data=payload,
            timeout=self.request_timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        self._update_viewstate(response)
        return response

    @staticmethod
    def _html_fragments(text: str) -> list[str]:
        fragments = re.findall(r"<!\[CDATA\[(.*?)\]\]>", text, flags=re.I | re.S)
        return [html.unescape(fragment) for fragment in fragments] or [html.unescape(text)]

    @classmethod
    def _soups(cls, text: str) -> list[BeautifulSoup]:
        return [BeautifulSoup(fragment, "html.parser") for fragment in cls._html_fragments(text)]

    @classmethod
    def _form_values(cls, text: str, form_name: str) -> dict[str, str]:
        values: dict[str, str] = {form_name: form_name}
        prefix = form_name + ":"
        for soup in cls._soups(text):
            for element in soup.find_all(["input", "select", "textarea"]):
                name = str(element.get("name") or "")
                if not (name == form_name or name.startswith(prefix)):
                    continue
                if element.has_attr("disabled"):
                    continue

                if element.name == "input":
                    input_type = str(element.get("type") or "text").casefold()
                    if input_type in {"submit", "button", "image", "reset", "file"}:
                        continue
                    if input_type in {"checkbox", "radio"} and not element.has_attr("checked"):
                        continue
                    values[name] = str(element.get("value") or "")
                elif element.name == "select":
                    selected = element.find("option", selected=True)
                    if selected is None:
                        selected = element.find("option")
                    values[name] = str(selected.get("value") or "") if selected else ""
                else:
                    values[name] = element.get_text()
        return values

    # -------------------------- Authentication --------------------------

    def login(self, username: str, password: str) -> None:
        if not username or not password:
            raise SEIConnectorError("Usuário e senha são obrigatórios.")

        with self.lock:
            response = self.session.get(LOGIN_URL, timeout=self.request_timeout)
            response.raise_for_status()
            self._update_viewstate(response)

            response = self._ajax_post(
                LOGIN_URL,
                self._click_payload(
                    "form",
                    "form:loginBtn:loginBtn",
                    {"form:usuario": username, "form:senha": password},
                ),
                referer=LOGIN_URL,
            )

            response = self._ajax_post(
                LOGIN_URL,
                self._click_payload(
                    "formPerfil",
                    "formPerfil:renderFormPerfil:renderFormPerfil",
                    {"org.richfaces.focus": ""},
                ),
                referer=LOGIN_URL,
            )

            response = self._ajax_post(
                LOGIN_URL,
                self._click_payload(
                    "formPerfil",
                    "formPerfil:logarDiretamenteComoFuncionario:logarDiretamenteComoFuncionario",
                    {"org.richfaces.focus": ""},
                ),
                referer=LOGIN_URL,
            )

            redirect = re.search(r'<redirect\s+url=["\']([^"\']+)["\']', response.text, flags=re.I)
            if redirect:
                target = urljoin(BASE, html.unescape(redirect.group(1)))
                self.session.get(target, timeout=self.request_timeout).raise_for_status()

            home = self.session.get(HOME_URL, timeout=self.request_timeout, allow_redirects=True)
            home.raise_for_status()
            self._update_viewstate(home)
            if "index.xhtml" in home.url.casefold():
                raise SEIConnectorError("Login não confirmado pelo SEI.")

            self.logged_in = True
            self.open_report_page()

    def open_report_page(self) -> None:
        if not self.logged_in:
            raise SEIConnectorError("Sessão do SEI não autenticada.")

        response = self.session.get(
            REPORT_URL,
            headers={"Referer": HOME_URL},
            timeout=self.request_timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        if "index.xhtml" in response.url.casefold():
            self.logged_in = False
            raise SEIConnectorError("A sessão do SEI expirou.")
        self._update_viewstate(response)
        if not self.viewstate:
            raise SEIConnectorError("Página do relatório abriu sem ViewState.")

        # Guarde os valores REAIS da tela atual. O SEI pode reabrir o relatório
        # preservando a última avaliação usada na sessão (questionário, datas e
        # até o ID dinâmico do campo de detalhamento). Serializar a própria tela
        # é mais robusto do que assumir j_idt76 ou valores fixos.
        self.report_page_text = response.text
        self.report_main_values = self._form_values(response.text, "form")

        # A chamada de base de conhecimento não é usada pelos cálculos, mas é
        # barata e mantém o fluxo próximo ao navegador real.
        try:
            self.session.get(
                KNOWLEDGE_URL,
                params={"rota": "/avaliacaoInstitucionalRel.xhtml"},
                headers={"Referer": REPORT_URL},
                timeout=self.request_timeout,
            )
        except requests.RequestException:
            pass

        self.report_open = True
        self.metadata = None
        self.last_search_results = {}
        self.last_search_form_values = {}

    # -------------------------- Evaluation search --------------------------

    @classmethod
    def parse_evaluation_results(cls, text: str) -> list[EvaluationSearchResult]:
        results: list[EvaluationSearchResult] = []
        for soup in cls._soups(text):
            for row in soup.find_all("tr", id=re.compile(r"^formAvaliacao:resultadoConsultaAvaliacao:\d+$")):
                name_link = row.find("a", id=re.compile(r":nome$"))
                if not name_link:
                    continue
                cells = [" ".join(td.stripped_strings).strip() for td in row.find_all("td")]
                values = [value for value in cells if value]
                results.append(
                    EvaluationSearchResult(
                        name=" ".join(name_link.stripped_strings).strip(),
                        source=str(name_link.get("id")),
                        start_date=values[1] if len(values) > 1 else None,
                        end_date=values[2] if len(values) > 2 else None,
                        target=values[3] if len(values) > 3 else None,
                        status=values[4] if len(values) > 4 else None,
                    )
                )
        # Partial responses podem conter o mesmo fragmento mais de uma vez.
        unique: dict[str, EvaluationSearchResult] = {}
        for result in results:
            unique[result.source] = result
        return list(unique.values())

    def search_evaluations(self, keyword: str) -> list[EvaluationSearchResult]:
        with self.lock:
            if not self.report_open:
                self.open_report_page()

            open_response = self._ajax_post(
                REPORT_URL,
                self._click_payload(
                    "form",
                    "form:consultaDadosAvaliacao:consultaDadosAvaliacao",
                    self._form_values_from_report_defaults(),
                ),
                referer=REPORT_URL,
            )

            response = open_response
            dialog_values = self._form_values(open_response.text, "formAvaliacao")
            if keyword.strip():
                dialog_values["formAvaliacao:consultaAvaliacao"] = "nome"
                dialog_values["formAvaliacao:valorConsultaAvaliacao"] = keyword.strip()
                response = self._ajax_post(
                    REPORT_URL,
                    self._click_payload(
                        "formAvaliacao",
                        "formAvaliacao:btnConsultarAvaliacao:btnConsultarAvaliacao",
                        dialog_values,
                    ),
                    referer=REPORT_URL,
                )

            results = self.parse_evaluation_results(response.text)
            self.last_search_results = {item.source: item for item in results}

            # Preserva o estado usado para gerar as linhas. Algumas respostas
            # parciais retornam só a tabela, então não podemos depender apenas
            # de reserializar o HTML devolvido: faça merge sobre os valores que
            # efetivamente foram enviados ao RichFaces.
            parsed_search_values = self._form_values(response.text, "formAvaliacao")
            dialog_values.update(
                {key: value for key, value in parsed_search_values.items() if key != "formAvaliacao"}
            )
            dialog_values.setdefault("formAvaliacao", "formAvaliacao")
            self.last_search_form_values = dialog_values
            return results

    def _form_values_from_report_defaults(self) -> dict[str, str]:
        # Use a serialização da tela real capturada no GET do relatório. Em HARs
        # diferentes o campo de detalhamento apareceu como form:j_idt76, porém
        # j_idt* é gerado pelo JSF e não deve ser fixado no cliente.
        values = dict(self.report_main_values or {"form": "form"})
        values.setdefault("form", "form")

        if self.metadata:
            values["form:questionario"] = self.metadata.selected_questionnaire_id or ""
            values["form:codigoUnidadeEnsino"] = self.metadata.unit_value or "2"
            values["form:turno"] = self.metadata.turn_value or "0"
            values["form:dataInicio:dataInicio"] = self.metadata.start_date or ""
            values["form:dataFim:dataFim"] = self.metadata.end_date or ""
            if self.metadata.detail_field_name:
                values[self.metadata.detail_field_name] = self.metadata.detail_value or "AVALIADO"

        # Fallback mínimo para uma página inesperadamente sem algum campo.
        values.setdefault("form:questionario", "")
        values.setdefault("form:codigoUnidadeEnsino", "2")
        values.setdefault("form:turno", "0")
        values.setdefault("form:dataInicio:dataInicio", "")
        values.setdefault("form:dataFim:dataFim", "")
        return values

    @classmethod
    def parse_evaluation_metadata(cls, text: str) -> EvaluationMetadata:
        evaluation_name = None
        start_date = None
        end_date = None
        questionnaires: list[QuestionnaireOption] = []
        selected_questionnaire_id = None
        selected_questionnaire_name = None
        question_count = 0
        detail_field_name = None
        detail_value = "AVALIADO"
        detail_options: list[ReportFilterOption] = []
        unit_value = "2"
        unit_options: list[ReportFilterOption] = []
        turn_value = "0"
        turn_options: list[ReportFilterOption] = []

        for soup in cls._soups(text):
            evaluation = soup.find(attrs={"id": "form:avaliacao"}) or soup.find(attrs={"name": "form:avaliacao"})
            if evaluation and evaluation.get("value"):
                evaluation_name = str(evaluation.get("value"))

            question_input = soup.find(attrs={"id": "form:pergunta"}) or soup.find(attrs={"name": "form:pergunta"})
            if question_input:
                match = re.search(r"(\d+)\s+Perguntas?\s+Selecionad", str(question_input.get("value") or ""), flags=re.I)
                if match:
                    question_count = int(match.group(1))

            select = soup.find("select", attrs={"name": "form:questionario"})
            if select:
                questionnaires = []
                for option in select.find_all("option"):
                    item = QuestionnaireOption(
                        sei_id=str(option.get("value") or ""),
                        name=" ".join(option.stripped_strings).strip(),
                        selected=option.has_attr("selected"),
                    )
                    questionnaires.append(item)
                    if item.selected:
                        selected_questionnaire_id = item.sei_id
                        selected_questionnaire_name = item.name
                if selected_questionnaire_id is None and questionnaires:
                    selected_questionnaire_id = questionnaires[0].sei_id
                    selected_questionnaire_name = questionnaires[0].name

            start = soup.find(attrs={"name": "form:dataInicio:dataInicio"})
            end = soup.find(attrs={"name": "form:dataFim:dataFim"})
            if start is not None:
                start_date = str(start.get("value") or "")
            if end is not None:
                end_date = str(end.get("value") or "")

            unit = soup.find("select", attrs={"name": "form:codigoUnidadeEnsino"})
            turn = soup.find("select", attrs={"name": "form:turno"})
            if unit:
                unit_options = [
                    ReportFilterOption(
                        value=str(opt.get("value") or ""),
                        label=" ".join(opt.stripped_strings).strip(),
                        selected=opt.has_attr("selected"),
                    )
                    for opt in unit.find_all("option")
                ]
                selected = unit.find("option", selected=True) or unit.find("option")
                value = str(selected.get("value") or "") if selected else ""
                if value:
                    unit_value = value
            if turn:
                turn_options = [
                    ReportFilterOption(
                        value=str(opt.get("value") or ""),
                        label=" ".join(opt.stripped_strings).strip(),
                        selected=opt.has_attr("selected"),
                    )
                    for opt in turn.find_all("option")
                ]
                selected = turn.find("option", selected=True) or turn.find("option")
                value = str(selected.get("value") or "") if selected else ""
                if value:
                    turn_value = value

            for candidate in soup.find_all("select", attrs={"name": True}):
                options = list(candidate.find_all("option"))
                option_values = {str(opt.get("value") or "") for opt in options}
                if {"AVALIADO", "TURMA", "GERAL"}.issubset(option_values):
                    detail_field_name = str(candidate.get("name"))
                    detail_options = [
                        ReportFilterOption(
                            value=str(opt.get("value") or ""),
                            label=" ".join(opt.stripped_strings).strip(),
                            selected=opt.has_attr("selected"),
                        )
                        for opt in options
                    ]
                    selected = candidate.find("option", selected=True) or candidate.find("option")
                    if selected:
                        detail_value = str(selected.get("value") or "AVALIADO")

        return EvaluationMetadata(
            evaluation_name=evaluation_name,
            start_date=start_date,
            end_date=end_date,
            questionnaires=questionnaires,
            selected_questionnaire_id=selected_questionnaire_id,
            selected_questionnaire_name=selected_questionnaire_name,
            question_count=question_count,
            detail_field_name=detail_field_name,
            detail_value=detail_value,
            detail_options=detail_options,
            unit_value=unit_value,
            unit_options=unit_options,
            turn_value=turn_value,
            turn_options=turn_options,
        )

    def select_evaluation(self, source: str) -> EvaluationMetadata:
        with self.lock:
            if source not in self.last_search_results:
                raise SEIConnectorError("Resultado de avaliação inválido ou expirado.")

            values = dict(self.last_search_form_values or {})
            values.setdefault("formAvaliacao", "formAvaliacao")
            values.setdefault("formAvaliacao:consultaAvaliacao", "nome")
            # Se a busca foi filtrada, preserve o texto realmente enviado; se o
            # diálogo veio sem filtro, mantenha vazio como no fluxo do navegador.
            values.setdefault("formAvaliacao:valorConsultaAvaliacao", "")
            response = self._ajax_post(
                REPORT_URL,
                self._click_payload("formAvaliacao", source, values),
                referer=REPORT_URL,
            )
            metadata = self.parse_evaluation_metadata(response.text)
            if not metadata.selected_questionnaire_id:
                raise SEIConnectorError("A avaliação selecionada não retornou um questionário.")
            selected_result = self.last_search_results[source]
            if not metadata.evaluation_name:
                metadata.evaluation_name = selected_result.name
            metadata.target = selected_result.target
            metadata.status = selected_result.status
            self.metadata = metadata
            return metadata

    def _main_form_values(self, *, questionnaire_id: str | None = None) -> dict[str, str]:
        if not self.metadata:
            raise SEIConnectorError("Selecione uma avaliação antes de continuar.")
        questionnaire = questionnaire_id or self.metadata.selected_questionnaire_id or ""
        values = {
            "form": "form",
            "form:questionario": questionnaire,
            "form:codigoUnidadeEnsino": self.metadata.unit_value or "2",
            "form:turno": self.metadata.turn_value or "0",
            "form:dataInicio:dataInicio": self.metadata.start_date or "",
            "form:dataFim:dataFim": self.metadata.end_date or "",
        }
        if self.metadata.detail_field_name:
            values[self.metadata.detail_field_name] = self.metadata.detail_value or "AVALIADO"
        return values

    def select_questionnaire(self, questionnaire_id: str) -> EvaluationMetadata:
        with self.lock:
            if not self.metadata:
                raise SEIConnectorError("Selecione uma avaliação primeiro.")
            valid = {item.sei_id for item in self.metadata.questionnaires}
            if questionnaire_id not in valid:
                raise SEIConnectorError("Questionário não pertence à avaliação selecionada.")
            if questionnaire_id == self.metadata.selected_questionnaire_id:
                return self.metadata

            values = self._main_form_values(questionnaire_id=questionnaire_id)
            response = self._ajax_post(
                REPORT_URL,
                self._change_payload("form", "form:questionario", values),
                referer=REPORT_URL,
            )
            previous = self.metadata
            updated = self.parse_evaluation_metadata(response.text)
            returned_form = self._form_values(response.text, "form")

            # Mudanças de <select> em JSF podem renderizar somente parte do
            # formulário. Preserve os campos da avaliação que não vierem no
            # partial-response em vez de substituí-los por vazio/default.
            updated.evaluation_name = updated.evaluation_name or previous.evaluation_name
            updated.start_date = updated.start_date or previous.start_date
            updated.end_date = updated.end_date or previous.end_date
            updated.target = updated.target or previous.target
            updated.status = updated.status or previous.status
            updated.question_count = updated.question_count or previous.question_count

            if not updated.questionnaires:
                updated.questionnaires = previous.questionnaires
            updated.selected_questionnaire_id = questionnaire_id
            selected = next(item for item in updated.questionnaires if item.sei_id == questionnaire_id)
            updated.selected_questionnaire_name = selected.name

            if not updated.detail_field_name:
                updated.detail_field_name = previous.detail_field_name
                updated.detail_value = previous.detail_value
                updated.detail_options = previous.detail_options
            elif not updated.detail_options:
                updated.detail_options = previous.detail_options
            if "form:codigoUnidadeEnsino" not in returned_form:
                updated.unit_value = previous.unit_value
                updated.unit_options = previous.unit_options
            elif not updated.unit_options:
                updated.unit_options = previous.unit_options
            if "form:turno" not in returned_form:
                updated.turn_value = previous.turn_value
                updated.turn_options = previous.turn_options
            elif not updated.turn_options:
                updated.turn_options = previous.turn_options

            self.metadata = updated
            return updated

    def configure_report(
        self, *, detail_value: str | None = None,
        unit_value: str | None = None, turn_value: str | None = None,
    ) -> EvaluationMetadata:
        """Aplica filtros descobertos na própria tela usando os eventos JSF reais.

        Os três seletores observados no HAR possuem ``change`` RichFaces. Em vez
        de apenas guardar o valor localmente, esta rotina envia o mesmo tipo de
        evento para manter o backing bean do SEI sincronizado antes de abrir as
        perguntas ou gerar o relatório. Nenhum ``j_idt`` é fixado: o campo de
        detalhamento continua sendo descoberto semanticamente.
        """
        with self.lock:
            if not self.metadata:
                raise SEIConnectorError("Selecione uma avaliacao primeiro.")

            def validate(value: str | None, options: list[ReportFilterOption], label: str) -> str | None:
                if value is None:
                    return None
                allowed = {item.value for item in options}
                if options and value not in allowed:
                    raise SEIConnectorError(f"{label} invalido para a tela atual do SEI.")
                return value

            desired = [
                (self.metadata.detail_field_name, validate(detail_value, self.metadata.detail_options, "Nivel de detalhamento"), "detail"),
                ("form:codigoUnidadeEnsino", validate(unit_value, self.metadata.unit_options, "Unidade"), "unit"),
                ("form:turno", validate(turn_value, self.metadata.turn_options, "Turno"), "turn"),
            ]

            for field_name, value, kind in desired:
                if value is None or not field_name:
                    continue
                current = {
                    "detail": self.metadata.detail_value,
                    "unit": self.metadata.unit_value,
                    "turn": self.metadata.turn_value,
                }[kind]
                if value == current:
                    continue

                values = self._main_form_values()
                values[field_name] = value
                response = self._ajax_post(
                    REPORT_URL,
                    self._change_payload("form", field_name, values),
                    referer=REPORT_URL,
                )
                previous = self.metadata
                updated = self.parse_evaluation_metadata(response.text)
                returned_form = self._form_values(response.text, "form")

                updated.evaluation_name = updated.evaluation_name or previous.evaluation_name
                updated.start_date = updated.start_date or previous.start_date
                updated.end_date = updated.end_date or previous.end_date
                updated.target = updated.target or previous.target
                updated.status = updated.status or previous.status
                updated.question_count = updated.question_count or previous.question_count
                if not updated.questionnaires:
                    updated.questionnaires = previous.questionnaires
                    updated.selected_questionnaire_id = previous.selected_questionnaire_id
                    updated.selected_questionnaire_name = previous.selected_questionnaire_name

                if not updated.detail_field_name:
                    updated.detail_field_name = previous.detail_field_name
                    updated.detail_value = previous.detail_value
                    updated.detail_options = previous.detail_options
                elif not updated.detail_options:
                    updated.detail_options = previous.detail_options
                if "form:codigoUnidadeEnsino" not in returned_form:
                    updated.unit_value = previous.unit_value
                    updated.unit_options = previous.unit_options
                elif not updated.unit_options:
                    updated.unit_options = previous.unit_options
                if "form:turno" not in returned_form:
                    updated.turn_value = previous.turn_value
                    updated.turn_options = previous.turn_options
                elif not updated.turn_options:
                    updated.turn_options = previous.turn_options

                # Partial responses frequentemente não devolvem o select alterado.
                # O valor enviado é a fonte de verdade para esse campo específico.
                if kind == "detail":
                    updated.detail_value = value
                elif kind == "unit":
                    updated.unit_value = value
                else:
                    updated.turn_value = value
                self.metadata = updated

            return self.metadata

    # -------------------------- Questions --------------------------

    @classmethod
    def _find_select_all_questions_source(cls, text: str) -> str | None:
        for soup in cls._soups(text):
            table = soup.find("table", id="formPergunta:resultadoConsultaPergunta")
            if not table:
                continue
            image = table.find("input", attrs={"type": "image", "src": re.compile(r"irFinal\.png", re.I)})
            if image and image.get("id"):
                return str(image.get("id"))
        return None

    @classmethod
    def _find_close_questions_source(cls, text: str) -> str | None:
        for soup in cls._soups(text):
            for link in soup.find_all("a", id=True):
                if " ".join(link.stripped_strings).strip().casefold() == "fechar":
                    return str(link.get("id"))
        return None

    @staticmethod
    def _question_count(text: str) -> int:
        match = re.search(r"(\d+)\s+Perguntas?\s+Selecionad", html.unescape(text), flags=re.I)
        return int(match.group(1)) if match else 0

    def prepare_all_questions(self, questionnaire_id: str | None = None) -> EvaluationMetadata:
        with self.lock:
            if questionnaire_id:
                self.select_questionnaire(questionnaire_id)
            if not self.metadata:
                raise SEIConnectorError("Selecione uma avaliação primeiro.")

            response = self._ajax_post(
                REPORT_URL,
                self._click_payload(
                    "form",
                    "form:consultaDadosPergunta:consultaDadosPergunta",
                    self._main_form_values(),
                ),
                referer=REPORT_URL,
            )

            select_all_source = self._find_select_all_questions_source(response.text)
            if not select_all_source:
                raise SEIConnectorError("Não encontrei o botão de selecionar todas as perguntas.")

            form_values = self._form_values(response.text, "formPergunta")
            selected = self._ajax_post(
                REPORT_URL,
                self._click_payload("formPergunta", select_all_source, form_values),
                referer=REPORT_URL,
            )
            count = self._question_count(selected.text)
            if count <= 0:
                raise SEIConnectorError("O SEI não confirmou nenhuma pergunta selecionada.")

            close_source = self._find_close_questions_source(selected.text)
            if not close_source:
                raise SEIConnectorError("Não encontrei o botão Fechar da seleção de perguntas.")
            close_values = self._form_values(selected.text, "formPergunta")
            closed = self._ajax_post(
                REPORT_URL,
                self._click_payload("formPergunta", close_source, close_values),
                referer=REPORT_URL,
            )

            closed_meta = self.parse_evaluation_metadata(closed.text)
            self.metadata.question_count = count
            if closed_meta.detail_field_name:
                self.metadata.detail_field_name = closed_meta.detail_field_name
                self.metadata.detail_value = closed_meta.detail_value
            return self.metadata

    # -------------------------- Report generation --------------------------

    @staticmethod
    def parse_progress(text: str) -> dict | None:
        decoded = html.unescape(text)
        excel = re.search(r"Gerando\s+EXCEL\s+(\d+)\s+de\s+(\d+)", decoded, flags=re.I)
        item = re.search(r"Item\s+(\d+)\s+de\s+(\d+)", decoded, flags=re.I)
        pct = re.search(r'class=["\']otm-progressbar-footer-pct["\'][^>]*>\s*(\d+)%', decoded, flags=re.I)
        if not any([excel, item, pct]):
            return None
        return {
            "excel_current": int(excel.group(1)) if excel else None,
            "excel_total": int(excel.group(2)) if excel else None,
            "item_current": int(item.group(1)) if item else None,
            "item_total": int(item.group(2)) if item else None,
            "percentage": int(pct.group(1)) if pct else None,
        }

    @staticmethod
    def _download_path(text: str) -> str | None:
        match = re.search(r"location\.href\s*=\s*['\"]([^'\"]*DownloadRelatorioSV[^'\"]+)['\"]", text, flags=re.I)
        return html.unescape(match.group(1)) if match else None

    @staticmethod
    def _filename_from_response(response: requests.Response, download_path: str) -> str:
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, flags=re.I)
        if match:
            return Path(match.group(1).strip()).name
        query = parse_qs(urlparse(download_path).query)
        if query.get("relatorio"):
            return Path(query["relatorio"][0]).name
        return "relatorio_sei.bin"

    @staticmethod
    def detect_file_kind(filename: str, content: bytes, content_type: str | None = None) -> str:
        suffix = Path(filename).suffix.casefold()
        if suffix == ".xlsx":
            return "xlsx"
        if suffix == ".zip":
            return "zip"

        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise SEIConnectorError("O SEI não devolveu um ZIP/XLSX válido.")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
                return "xlsx"
        return "zip"

    def generate_report(self, *, max_wait_seconds: int = 300, poll_interval: float = 1.5) -> DownloadedReport:
        with self.lock:
            if not self.metadata or self.metadata.question_count <= 0:
                raise SEIConnectorError("Prepare as perguntas antes de gerar o relatório.")

            response = self._ajax_post(
                REPORT_URL,
                self._click_payload(
                    "form",
                    "form:botaoGerarRelatorioEmExcel",
                    self._main_form_values(),
                ),
                referer=REPORT_URL,
            )
            self.last_progress = self.parse_progress(response.text)

            deadline = time.monotonic() + max_wait_seconds
            done = False
            while time.monotonic() < deadline:
                pool = self._ajax_post(
                    REPORT_URL,
                    self._component_payload("statusPanelBaixa", "statusPanelBaixa:statusPanelBaixa_pool2"),
                    referer=REPORT_URL,
                )
                progress = self.parse_progress(pool.text)
                if progress:
                    self.last_progress = progress

                encerrado = self._ajax_post(
                    REPORT_URL,
                    self._component_payload("statusPanelBaixa", "statusPanelBaixa:statusPanelBaixa_encerrar"),
                    referer=REPORT_URL,
                )
                progress = self.parse_progress(encerrado.text)
                if progress:
                    self.last_progress = progress

                if "executarOncomplete2();" in encerrado.text or "executarOncomplete2();" in pool.text:
                    done = True
                    break
                time.sleep(poll_interval)

            if not done:
                raise SEIConnectorError(
                    f"O SEI não concluiu o relatório em {max_wait_seconds} segundos."
                )

            final = self._ajax_post(
                REPORT_URL,
                self._component_payload("statusPanelBaixa", "statusPanelBaixa:statusPanelBaixa_oncomplete2"),
                referer=REPORT_URL,
            )
            download_path = self._download_path(final.text)
            if not download_path:
                raise SEIConnectorError("O SEI concluiu o processamento, mas não informou o arquivo final.")

            download_url = urljoin(BASE, download_path)
            file_response = self.session.get(
                download_url,
                headers={"Referer": REPORT_URL},
                timeout=max(self.request_timeout, 120),
                allow_redirects=True,
            )
            file_response.raise_for_status()
            content = file_response.content
            filename = self._filename_from_response(file_response, download_path)
            kind = self.detect_file_kind(filename, content, file_response.headers.get("Content-Type"))

            return DownloadedReport(
                filename=filename,
                content=content,
                kind=kind,
                content_type=file_response.headers.get("Content-Type"),
                download_path=download_path,
                progress=self.last_progress,
            )

    def close(self) -> None:
        with self.lock:
            self.session.close()
            self.logged_in = False
            self.report_open = False
            self.metadata = None
            self.report_page_text = ""
            self.report_main_values = {}
            self.last_search_results = {}
            self.last_search_form_values = {}
