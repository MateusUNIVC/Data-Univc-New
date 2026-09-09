from __future__ import annotations

"""Consulta individual de datas de curso no SEI para o módulo DM.

Adaptado do utilitário ``sei_datas_curso_por_nome.py`` e integrado ao DM desde a v0.7.9; na v0.8.0, ``dataConclusaoCurso`` é traduzida para a data de defesa do domínio.
A integração mantém as credenciais apenas em memória durante a requisição e não
persiste HTML/XML com dados pessoais por padrão.
"""

import html
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://sei.ivc.br"
LOGIN_URL = f"{BASE}/index.xhtml"
HOME_URL = f"{BASE}/visaoAdministrativo/administrativo/homeAdministrador.xhtml"
ALTER_URL = f"{BASE}/visaoAdministrativo/academico/alteracoesCadastraisMatricula.xhtml"
KNOWLEDGE_URL = f"{BASE}/webservice/baseconhecimento/ativos"


class SEIStudentDatesError(RuntimeError):
    pass


class SEIStudentNotFound(SEIStudentDatesError):
    pass


class SEIStudentAmbiguous(SEIStudentDatesError):
    pass


def normalize_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def parse_sei_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


@dataclass(slots=True)
class StudentDatesTarget:
    student_id: int | None
    student_code: str
    student_name: str
    cohort_opening_date: date | None = None
    area_code: str | None = None
    cohort_number: int | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "StudentDatesTarget":
        raw_opening = payload.get("cohort_opening_date") or payload.get("opening_date")
        opening = parse_sei_date(raw_opening)
        return cls(
            student_id=int(payload["student_id"]) if payload.get("student_id") not in (None, "") else None,
            student_code=str(payload.get("student_code") or payload.get("matricula") or "").strip(),
            student_name=str(payload.get("student_name") or payload.get("nome") or "").strip(),
            cohort_opening_date=opening,
            area_code=str(payload.get("area_code") or "").strip().upper() or None,
            cohort_number=int(payload["cohort_number"]) if payload.get("cohort_number") not in (None, "") else None,
        )


class SEIStudentDatesBot:
    def __init__(self, *, debug_dir: Path | None = None, verbose: bool = False) -> None:
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
        self.viewstate: str | None = None
        self.debug_dir = debug_dir
        self.verbose = bool(verbose)
        if self.debug_dir is not None:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _say(self, message: str) -> None:
        if self.verbose:
            print(message)

    def save_debug(self, name: str, response: requests.Response) -> None:
        if self.debug_dir is not None:
            (self.debug_dir / name).write_bytes(response.content)

    @staticmethod
    def extract_viewstate(text: str) -> str | None:
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

    def update_viewstate(self, response: requests.Response) -> None:
        value = self.extract_viewstate(response.text)
        if value:
            self.viewstate = value

    @staticmethod
    def click_payload(form: str, source: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        data = {
            form: form,
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
        if extra:
            data.update(extra)
        return data

    def ajax_post(self, url: str, data: dict[str, str], *, referer: str) -> requests.Response:
        if not self.viewstate:
            raise SEIStudentDatesError("ViewState não carregado pelo SEI.")
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
            },
            data=payload,
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()
        self.update_viewstate(response)
        return response

    def login(self, username: str, password: str) -> None:
        response = self.session.get(LOGIN_URL, timeout=60)
        response.raise_for_status()
        self.update_viewstate(response)
        if not self.viewstate:
            raise SEIStudentDatesError("ViewState não encontrado na tela de login.")

        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "form",
                "form:loginBtn:loginBtn",
                {"form:usuario": username, "form:senha": password},
            ),
            referer=LOGIN_URL,
        )
        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "formPerfil",
                "formPerfil:renderFormPerfil:renderFormPerfil",
                {"org.richfaces.focus": ""},
            ),
            referer=LOGIN_URL,
        )
        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "formPerfil",
                "formPerfil:logarDiretamenteComoFuncionario:logarDiretamenteComoFuncionario",
                {"org.richfaces.focus": ""},
            ),
            referer=LOGIN_URL,
        )
        redirect = re.search(r'<redirect\s+url=["\']([^"\']+)["\']', response.text, flags=re.I)
        if redirect:
            self.session.get(urljoin(BASE, html.unescape(redirect.group(1))), timeout=60).raise_for_status()
        response = self.session.get(HOME_URL, timeout=60, allow_redirects=True)
        response.raise_for_status()
        self.update_viewstate(response)
        if "index.xhtml" in response.url.lower():
            raise SEIStudentDatesError("Login não confirmado pelo SEI.")

    def abrir_pagina(self) -> None:
        response = self.session.get(ALTER_URL, headers={"Referer": HOME_URL}, timeout=60)
        response.raise_for_status()
        self.update_viewstate(response)
        self.save_debug("alteracoes_inicial.html", response)
        self.session.get(
            KNOWLEDGE_URL,
            params={"rota": "/alteracoesCadastraisMatricula.xhtml"},
            headers={"Referer": ALTER_URL},
            timeout=60,
        ).raise_for_status()

    def abrir_dialogo_aluno(self, nome: str) -> requests.Response:
        source = "form:consultaDadosAluno:consultaDadosAluno"
        response = self.ajax_post(
            ALTER_URL,
            self.click_payload(
                "form",
                source,
                {
                    "form:j_idt438-value": "tabMatricula",
                    "form:alunoMatricula": "",
                    "form:alunoNome": nome,
                    "form:cursoMatricula": "",
                },
            ),
            referer=ALTER_URL,
        )
        self.save_debug("dialogo_aluno.xml", response)
        return response

    def pesquisar_aluno(self, nome: str) -> requests.Response:
        source = "formAluno:btnConsultar:btnConsultar"
        response = self.ajax_post(
            ALTER_URL,
            self.click_payload(
                "formAluno",
                source,
                {
                    "formAluno:consultaAluno": "nomePessoa",
                    "formAluno:valorConsultaAluno": nome,
                },
            ),
            referer=ALTER_URL,
        )
        self.save_debug("resultado_pesquisa.xml", response)
        return response

    @staticmethod
    def extrair_resultados(text: str) -> list[dict[str, str]]:
        decoded = html.unescape(text)
        blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', decoded, flags=re.I | re.S) or [decoded]
        results: list[dict[str, str]] = []
        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")
            for row in soup.find_all("tr"):
                row_text = " ".join(row.stripped_strings).strip()
                for element in row.find_all(["a", "button"], attrs={"id": True}):
                    element_id = str(element.get("id"))
                    onclick = str(element.get("onclick") or "")
                    if (
                        "formAluno:resultadoConsultaAluno:" in element_id
                        and "RichFaces.ajax" in onclick
                        and "tooltip" not in element_id.casefold()
                    ):
                        results.append({"texto": row_text, "source": element_id})
                        break
        if not results:
            for full_id, _ in re.findall(
                r'(formAluno:resultadoConsultaAluno:\d+:(j_idt\d+):\2)',
                decoded,
                flags=re.I,
            ):
                results.append({"texto": "", "source": full_id})
        unique: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in results:
            if item["source"] not in seen:
                seen.add(item["source"])
                unique.append(item)
        return unique

    def escolher_resultado(
        self,
        nome: str,
        response: requests.Response,
        *,
        expected_student_code: str | None = None,
    ) -> dict[str, str]:
        results = self.extrair_resultados(response.text)
        if not results:
            raise SEIStudentNotFound("Nenhum resultado foi encontrado para o aluno no SEI.")

        name_token = normalize_text(nome)
        matches = [
            item
            for item in results
            if not item["texto"] or name_token in normalize_text(item["texto"])
        ]
        if not matches:
            raise SEIStudentNotFound("Nenhum resultado compatível com o nome foi encontrado no SEI.")

        if expected_student_code:
            code_token = normalize_identifier(expected_student_code)
            code_matches = [
                item
                for item in matches
                if code_token and code_token in normalize_identifier(item["texto"])
            ]
            if len(code_matches) == 1:
                return code_matches[0]

        if len(matches) == 1:
            return matches[0]
        raise SEIStudentAmbiguous(
            "Há mais de um resultado compatível no SEI e a matrícula não foi suficiente para resolver o homônimo."
        )

    def selecionar_aluno(self, nome: str, item: dict[str, str]) -> requests.Response:
        source = item["source"]
        response = self.ajax_post(
            ALTER_URL,
            self.click_payload(
                "formAluno",
                source,
                {
                    "formAluno:consultaAluno": "nomePessoa",
                    "formAluno:valorConsultaAluno": nome,
                },
            ),
            referer=ALTER_URL,
        )
        self.save_debug("aluno_selecionado.xml", response)
        return response

    @staticmethod
    def extrair_inputs(text: str) -> dict[str, str]:
        decoded = html.unescape(text)
        blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', decoded, flags=re.I | re.S) or [decoded]
        values: dict[str, str] = {}
        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")
            for element in soup.find_all(["input", "textarea", "select"]):
                key = str(element.get("name") or element.get("id") or "").strip()
                if not key:
                    continue
                if element.name == "select":
                    option = element.find("option", selected=True)
                    value = option.get("value", "") if option else ""
                elif element.name == "textarea":
                    value = element.get_text()
                else:
                    value = element.get("value", "")
                values[key] = html.unescape(str(value)).strip()
        return values

    @staticmethod
    def valor(values: dict[str, str], key_fragment: str) -> str | None:
        if key_fragment in values:
            return values[key_fragment]
        needle = key_fragment.casefold()
        for key, value in values.items():
            if key.casefold().endswith(needle):
                return value
        for key, value in values.items():
            if needle in key.casefold():
                return value
        return None

    def extrair_dados(self, response: requests.Response) -> dict[str, Any]:
        values = self.extrair_inputs(response.text)
        nome = self.valor(values, "form:alunoNome")
        matricula = self.valor(values, "form:alunoMatricula")
        curso = self.valor(values, "form:cursoMatricula")
        indices: set[int] = set()
        for key in values:
            match = re.search(r'form:alunosTurma:(\d+):', key, flags=re.I)
            if match:
                indices.add(int(match.group(1)))
        links: list[dict[str, Any]] = []
        for index in sorted(indices):
            prefix = f"form:alunosTurma:{index}:"
            start = self.valor(values, prefix + "dataInicioCurso:dataInicioCurso")
            completion = self.valor(values, prefix + "dataConclusaoCurso:dataConclusaoCurso")
            year = self.valor(values, prefix + "anoIngresso")
            semester = self.valor(values, prefix + "semestreIngresso")
            # Algumas versões do SEI carregam o número/rótulo da turma em um
            # input oculto da mesma linha. Capturá-lo torna a seleção de vínculo
            # segura mesmo quando a turma ainda não possui data de abertura.
            cohort_hint = None
            for key, value in values.items():
                if not key.casefold().startswith(prefix.casefold()) or not value:
                    continue
                suffix = key[len(prefix):]
                normalized_suffix = re.sub(r"[^a-z0-9]+", "", normalize_text(suffix))
                if "turma" in normalized_suffix and "alunosturma" not in normalized_suffix:
                    cohort_hint = str(value).strip()
                    break
            if any(value is not None for value in (start, completion, year, semester, cohort_hint)):
                links.append(
                    {
                        "indice": index,
                        "data_inicio_curso": start or None,
                        "data_conclusao_curso": completion or None,
                        "ano_ingresso": year or None,
                        "semestre_ingresso": semester or None,
                        "turma": cohort_hint or None,
                    }
                )
        if not any([nome, matricula, curso, links]):
            raise SEIStudentDatesError("O SEI retornou o aluno, mas não trouxe os campos de vínculo esperados.")
        return {"nome": nome, "matricula": matricula, "curso": curso, "vinculos": links}

    def consultar(self, nome: str, *, expected_student_code: str | None = None) -> dict[str, Any]:
        self.abrir_pagina()
        self.abrir_dialogo_aluno(nome)
        search = self.pesquisar_aluno(nome)
        selected_item = self.escolher_resultado(
            nome,
            search,
            expected_student_code=expected_student_code,
        )
        selected = self.selecionar_aluno(nome, selected_item)
        result = self.extrair_dados(selected)
        if expected_student_code and result.get("matricula"):
            if normalize_identifier(result["matricula"]) != normalize_identifier(expected_student_code):
                raise SEIStudentAmbiguous(
                    "O registro selecionado pelo SEI retornou matrícula diferente da matrícula cadastrada."
                )
        return result


def choose_course_link(result: dict[str, Any], target: StudentDatesTarget) -> dict[str, Any]:
    links = list(result.get("vinculos") or [])
    if not links:
        raise SEIStudentDatesError("O aluno foi localizado, mas não possui vínculo de curso com datas no SEI.")
    if len(links) == 1:
        chosen = links[0]
        rule = "unico_vinculo"
    else:
        candidates = links
        if target.cohort_number is not None:
            by_cohort = []
            for row in candidates:
                hint = str(row.get("turma") or "")
                numbers = {int(value) for value in re.findall(r"\d+", hint)}
                if int(target.cohort_number) in numbers:
                    by_cohort.append(row)
            if len(by_cohort) == 1:
                chosen = by_cohort[0]
                rule = "numero_turma"
                candidates = []
        opening = target.cohort_opening_date
        if candidates and opening:
            semester = 1 if opening.month <= 6 else 2
            exact = [
                row
                for row in candidates
                if str(row.get("ano_ingresso") or "").strip() == str(opening.year)
                and str(row.get("semestre_ingresso") or "").strip() in {str(semester), f"{semester}.0"}
            ]
            if len(exact) == 1:
                chosen = exact[0]
                rule = "ano_semestre_turma"
            else:
                same_year = [
                    row
                    for row in candidates
                    if str(row.get("ano_ingresso") or "").strip() == str(opening.year)
                ]
                if len(same_year) == 1:
                    chosen = same_year[0]
                    rule = "ano_turma"
                else:
                    raise SEIStudentAmbiguous(
                        "O aluno possui múltiplos vínculos no SEI e não foi possível identificar com segurança qual pertence à turma do DM."
                    )
        elif candidates:
            raise SEIStudentAmbiguous(
                "O aluno possui múltiplos vínculos no SEI e não foi possível identificar com segurança qual pertence à turma selecionada."
            )

    start = parse_sei_date(chosen.get("data_inicio_curso"))
    completion = parse_sei_date(chosen.get("data_conclusao_curso"))
    if chosen.get("data_inicio_curso") and not start:
        raise SEIStudentDatesError("A data de início retornada pelo SEI possui formato não reconhecido.")
    if chosen.get("data_conclusao_curso") and not completion:
        raise SEIStudentDatesError("A data de conclusão retornada pelo SEI possui formato não reconhecido.")
    if start and completion and completion < start:
        raise SEIStudentDatesError("O SEI retornou uma conclusão anterior ao início do curso.")
    return {
        "student_id": target.student_id,
        "student_code": target.student_code,
        "student_name": target.student_name,
        "sei_student_code": str(result.get("matricula") or "").strip() or None,
        "course": str(result.get("curso") or "").strip() or None,
        "course_start_date": start.isoformat() if start else None,
        "defense_date": completion.isoformat() if completion else None,
        "admission_year": chosen.get("ano_ingresso") or None,
        "admission_semester": chosen.get("semestre_ingresso") or None,
        "link_selection_rule": rule,
        "link_count": len(links),
        "ok": True,
    }


def lookup_student_course_dates(
    username: str,
    password: str,
    targets: Iterable[dict[str, Any] | StudentDatesTarget],
    *,
    debug_dir: Path | None = None,
) -> dict[str, Any]:
    prepared = [item if isinstance(item, StudentDatesTarget) else StudentDatesTarget.from_mapping(item) for item in targets]
    if not prepared:
        return {"items": [], "summary": {"requested": 0, "found": 0, "failed": 0, "defenses_found": 0}}
    if not str(username or "").strip() or not password:
        raise SEIStudentDatesError("Informe usuário e senha do SEI.")

    bot = SEIStudentDatesBot(debug_dir=debug_dir, verbose=False)
    bot.login(str(username).strip(), password)
    items: list[dict[str, Any]] = []
    for target in prepared:
        try:
            if not target.student_name or not target.student_code:
                raise SEIStudentDatesError("Nome e matrícula são obrigatórios para consultar o aluno.")
            result = bot.consultar(target.student_name, expected_student_code=target.student_code)
            items.append(choose_course_link(result, target))
        except SEIStudentAmbiguous as exc:
            items.append(
                {
                    "student_id": target.student_id,
                    "student_code": target.student_code,
                    "student_name": target.student_name,
                    "ok": False,
                    "error_type": "ambiguous",
                    "error": str(exc),
                }
            )
        except (SEIStudentDatesError, requests.RequestException) as exc:
            items.append(
                {
                    "student_id": target.student_id,
                    "student_code": target.student_code,
                    "student_name": target.student_name,
                    "ok": False,
                    "error_type": "lookup",
                    "error": str(exc),
                }
            )

    found = sum(1 for item in items if item.get("ok"))
    defenses_found = sum(1 for item in items if item.get("ok") and item.get("defense_date"))
    start_found = sum(1 for item in items if item.get("ok") and item.get("course_start_date"))
    return {
        "items": items,
        "summary": {
            "requested": len(items),
            "found": found,
            "failed": len(items) - found,
            "start_dates_found": start_found,
            "defenses_found": defenses_found,
        },
        "credentials_persisted": False,
    }
