#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SEI/UNIVC - Relatório Alunos por Unidade / Curso / Turma
Fluxo específico: STRICTO SENSU + periodicidade INTEGRAL + Excel Sintético

Baseado na sequência de requisições capturada no navegador:
- abre o relatório;
- abre a seleção de Unidade de Ensino;
- seleciona STRICTO SENSU;
- altera periodicidade para INTEGRAL;
- abre a seleção de cursos;
- seleciona:
    58 - Ciência, Tecnologia e Educação
    228 - Saúde e Desigualdade Social
- aciona "imprimirExcelSintetico";
- extrai a URL /DownloadRelatorioSV?relatorio=....xlsx;
- baixa o XLSX.

Dependências:
    pip install requests beautifulsoup4

Uso:
    python sei_alunos_stricto_sensu_integral_v2.py

Opcional:
    python sei_alunos_stricto_sensu_integral_v2.py --ano 2025
"""

from __future__ import annotations

import argparse
import getpass
import html
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://sei.ivc.br"
LOGIN_URL = f"{BASE}/index.xhtml"
HOME_URL = f"{BASE}/visaoAdministrativo/administrativo/homeAdministrador.xhtml"
REPORT_URL = (
    f"{BASE}/visaoAdministrativo/academico/relatorio/"
    "alunosPorUnidadeCursoTurmaRel.xhtml"
)
MENU_JS_URL = f"{BASE}/javax.faces.resource/script/menuTopo.js.xhtml?ver=1.1"
KNOWLEDGE_URL = f"{BASE}/webservice/baseconhecimento/ativos"

SCRIPT_DIR = Path(__file__).resolve().parent
DEBUG_DIR = SCRIPT_DIR / "debug_sei_stricto"

STRICTO_UNIT_TOKEN = "STRICTO SENSU"
STRICTO_UNIT_VALUE = "CENTRO UNIVERSITÁRIO VALE DO CRICARÉ - STRICTO SENSU; "

STRICTO_COURSES = [
    "58 - Ciência, Tecnologia e Educação",
    "228 - Saúde e Desigualdade Social",
]

STRICTO_COURSES_VALUE = (
    "58 - Ciência, Tecnologia e Educação; "
    "228 - Saúde e Desigualdade Social; "
)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


class SEIStrictoBot:
    def __init__(self, *, debug_dir: Path | None = None, verbose: bool = True) -> None:
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
        self.report_html = ""
        self.debug_dir = debug_dir
        self.verbose = bool(verbose)
        if self.debug_dir is not None:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    def _say(self, message: str = "") -> None:
        if self.verbose:
            print(message)

    def save_debug(self, name: str, response: requests.Response) -> Path | None:
        if self.debug_dir is None:
            return None
        path = self.debug_dir / name
        path.write_bytes(response.content)
        return path

    @staticmethod
    def extract_viewstate(text: str) -> str | None:
        soup = BeautifulSoup(text, "html.parser")
        field = soup.find("input", attrs={"name": "javax.faces.ViewState"})
        if field and field.get("value"):
            return html.unescape(str(field["value"]))

        patterns = [
            (
                r'<update[^>]+id=["\'][^"\']*javax\.faces\.ViewState'
                r'[^"\']*["\'][^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</update>'
            ),
            (
                r'<update[^>]+id=["\'][^"\']*javax\.faces\.ViewState'
                r'[^"\']*["\'][^>]*>(.*?)</update>'
            ),
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                return html.unescape(match.group(1).strip())
        return None

    def update_viewstate(self, response: requests.Response) -> None:
        value = self.extract_viewstate(response.text)
        if value:
            self.viewstate = value

    @staticmethod
    def click_payload(
        form: str,
        source: str,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        payload = {
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
            payload.update(extra)
        return payload

    def ajax_post(
        self,
        url: str,
        payload: dict[str, str],
        *,
        referer: str,
    ) -> requests.Response:
        if not self.viewstate:
            raise RuntimeError("javax.faces.ViewState não carregado.")

        data = dict(payload)
        data["javax.faces.ViewState"] = self.viewstate

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
            data=data,
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()
        self.update_viewstate(response)
        return response

    def login(self, username: str, password: str) -> None:
        self._say("[LOGIN 1/4] Abrindo login...")
        response = self.session.get(LOGIN_URL, timeout=60)
        response.raise_for_status()
        self.update_viewstate(response)

        if not self.viewstate:
            self.save_debug("login_inicial.html", response)
            raise RuntimeError("ViewState não encontrado na tela de login.")

        self._say("[LOGIN 2/4] Enviando usuário e senha...")
        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "form",
                "form:loginBtn:loginBtn",
                {
                    "form:usuario": username,
                    "form:senha": password,
                },
            ),
            referer=LOGIN_URL,
        )
        self.save_debug("login_1.xml", response)

        self._say("[LOGIN 3/4] Renderizando perfil...")
        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "formPerfil",
                "formPerfil:renderFormPerfil:renderFormPerfil",
                {"org.richfaces.focus": ""},
            ),
            referer=LOGIN_URL,
        )
        self.save_debug("login_2.xml", response)

        self._say("[LOGIN 4/4] Entrando como funcionário...")
        response = self.ajax_post(
            LOGIN_URL,
            self.click_payload(
                "formPerfil",
                (
                    "formPerfil:logarDiretamenteComoFuncionario:"
                    "logarDiretamenteComoFuncionario"
                ),
                {"org.richfaces.focus": ""},
            ),
            referer=LOGIN_URL,
        )
        self.save_debug("login_3.xml", response)

        redirect = re.search(
            r'<redirect\s+url=["\']([^"\']+)["\']',
            response.text,
            flags=re.I,
        )
        if redirect:
            target = urljoin(BASE, html.unescape(redirect.group(1)))
            self.session.get(target, timeout=60).raise_for_status()

        response = self.session.get(HOME_URL, timeout=60, allow_redirects=True)
        response.raise_for_status()

        if "index.xhtml" in response.url.lower():
            raise RuntimeError("Login não confirmado pelo SEI.")

        self.update_viewstate(response)
        self._say("          Login confirmado.")

    def abrir_relatorio(self) -> None:
        self._say("[1/9] Abrindo área acadêmica...")

        response = self.session.get(HOME_URL, timeout=60)
        response.raise_for_status()
        self.update_viewstate(response)

        response = self.ajax_post(
            HOME_URL,
            self.click_payload("formMenuLateral", "menuAcad"),
            referer=HOME_URL,
        )
        self.save_debug("menu_academico.xml", response)

        self.session.get(
            MENU_JS_URL,
            headers={"Referer": HOME_URL},
            timeout=60,
        ).raise_for_status()

        self._say("[2/9] Abrindo Alunos por Unidade/Curso/Turma...")
        response = self.session.get(
            REPORT_URL,
            headers={"Referer": HOME_URL},
            timeout=60,
        )
        response.raise_for_status()

        self.report_html = response.text
        self.update_viewstate(response)
        self.save_debug("relatorio_inicial.html", response)

        self.session.get(
            KNOWLEDGE_URL,
            params={"rota": "/alunosPorUnidadeCursoTurmaRel.xhtml"},
            headers={"Referer": REPORT_URL},
            timeout=60,
        ).raise_for_status()

    @staticmethod
    def form_principal(
        *,
        unidade: str,
        periodicidade: str,
        tipo_aluno: str = "normal",
        ano: str | None = None,
        semestre: str | None = None,
        cursos: str = "",
    ) -> dict[str, str]:
        data = {
            "form": "form",
            "form:unidadeEnsino": unidade,
            "form:unidadeEnsinoPolo": "",
            "form:periodicidade": periodicidade,
            "form:nomeCurso": cursos,
            "form:nomeTurno": "",
            "form:turma": "",
            "form:disciplina": "",
            "form:j_idt417": "ambos",
            "form:tipoMatricula": "",
            "form:tipoAluno": tipo_aluno,
            "form:tipoRelatorio": "SI",
            "form:data:data": "",
            "form:dataFim:dataFim": "",
            "form:OrdenacaoAluno": "ALUNO",
            "form:valorConsultaPeriodoLetivo": "0",
            "form:j_idt464:j_idt464": "on",
            "form:j_idt534:j_idt534": "on",
            "form:j_idt545:j_idt545": "on",
            "form:j_idt552:j_idt552": "on",
        }

        if ano is not None:
            data["form:ano"] = ano
        if semestre is not None:
            data["form:semestreNotaAluno"] = semestre

        return data

    def abrir_dialogo_unidade(self, ano: str) -> requests.Response:
        """
        Reproduz o estado observado na captura:
        ao abrir o diálogo, a tela ainda estava em SEMESTRAL e ano 2025.
        A periodicidade só vira INTEGRAL depois da seleção da unidade.
        """
        self._say("[3/9] Abrindo diálogo da Unidade de Ensino...")

        # Na captura real, o campo continha a lista inteira de unidades.
        # Não é necessário hardcodar essa lista; o clique abre o mesmo diálogo.
        payload = self.click_payload(
            "form",
            "form:selecionarUnidadeEnsino:selecionarUnidadeEnsino",
            self.form_principal(
                unidade="",
                periodicidade="SEMESTRAL",
                ano=ano,
                semestre="",
                tipo_aluno="normal",
            ),
        )

        response = self.ajax_post(
            REPORT_URL,
            payload,
            referer=REPORT_URL,
        )
        self.save_debug("01_dialogo_unidade.xml", response)
        return response

    @staticmethod
    def extract_clickable_rows(
        response_text: str,
        *,
        table_marker: str,
    ) -> list[tuple[str, str]]:
        decoded = html.unescape(response_text)
        blocks = re.findall(
            r'<!\[CDATA\[(.*?)\]\]>',
            decoded,
            flags=re.I | re.S,
        ) or [decoded]

        rows: list[tuple[str, str]] = []

        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")

            for row in soup.find_all("tr"):
                row_text = " ".join(row.stripped_strings).strip()
                if not row_text:
                    continue

                sources: list[str] = []

                for element in row.find_all(
                    ["a", "button"],
                    attrs={"id": True},
                ):
                    element_id = str(element.get("id"))
                    onclick = str(element.get("onclick") or "")

                    if (
                        table_marker in element_id
                        and "RichFaces.ajax" in onclick
                        and "tooltip" not in element_id.casefold()
                    ):
                        sources.append(element_id)

                if sources:
                    rows.append((row_text, sources[-1]))

        return rows

    @staticmethod
    def find_source_by_regex(
        text: str,
        pattern: str,
    ) -> str | None:
        match = re.search(pattern, html.unescape(text), flags=re.I)
        return match.group(1) if match else None

    def preparar_lista_unidades(
        self,
        dialog_response: requests.Response,
    ) -> requests.Response:
        """
        A captura executou antes da seleção:
            formpanelUnidadeEnsino:filtrosUnidadeEnsino2:j_idt273

        Tentamos descobrir dinamicamente esse componente; caso não apareça
        no HTML, usamos o ID capturado como fallback.
        """
        self._say("[4/9] Preparando lista de unidades...")

        source = self.find_source_by_regex(
            dialog_response.text,
            r'((?:formpanelUnidadeEnsino:)'
            r'filtrosUnidadeEnsino2:(?:\d+:)?j_idt\d+)',
        )

        if not source:
            source = "formpanelUnidadeEnsino:filtrosUnidadeEnsino2:j_idt273"

        self._say(f"          JSF source filtro: {source}")

        response = self.ajax_post(
            REPORT_URL,
            self.click_payload(
                "formpanelUnidadeEnsino",
                source,
                {
                    "formpanelUnidadeEnsino:panelUnidadeEnsino_table:j_idt258": "",
                    "formpanelUnidadeEnsino:filtrosUnidadeEnsino2:j_idt279": "",
                },
            ),
            referer=REPORT_URL,
        )
        self.save_debug("02_lista_unidades.xml", response)
        return response

    def selecionar_stricto(
        self,
        response: requests.Response,
    ) -> None:
        self._say("[5/9] Selecionando STRICTO SENSU...")

        rows = self.extract_clickable_rows(
            response.text,
            table_marker="formpanelUnidadeEnsino:panelUnidadeEnsino_table:",
        )

        self._say("          Unidades detectadas:")
        for text, _ in rows:
            self._say(f"          - {text}")

        target = normalize_text(STRICTO_UNIT_TOKEN)
        matches = [
            (text, source)
            for text, source in rows
            if target in normalize_text(text)
        ]

        if len(matches) == 1:
            row_text, source = matches[0]
        else:
            # Fallback exato da captura: STRICTO era a linha 5.
            source = self.find_source_by_regex(
                response.text,
                r'(formpanelUnidadeEnsino:panelUnidadeEnsino_table:5:j_idt\d+)',
            )
            if not source:
                source = (
                    "formpanelUnidadeEnsino:"
                    "panelUnidadeEnsino_table:5:j_idt268"
                )
            row_text = STRICTO_UNIT_VALUE

        self._say(f"          Selecionada: {row_text}")
        self._say(f"          JSF source: {source}")

        result = self.ajax_post(
            REPORT_URL,
            self.click_payload(
                "formpanelUnidadeEnsino",
                source,
                {
                    "formpanelUnidadeEnsino:panelUnidadeEnsino_table:j_idt258": "",
                    "formpanelUnidadeEnsino:filtrosUnidadeEnsino2:j_idt279": "",
                },
            ),
            referer=REPORT_URL,
        )
        self.save_debug("03_stricto_selecionado.xml", result)

    def mudar_para_integral(self, ano: str) -> requests.Response:
        self._say("[6/9] Mudando periodicidade para INTEGRAL...")

        source = "form:periodicidade"
        data = self.form_principal(
            unidade=STRICTO_UNIT_VALUE,
            periodicidade="INTEGRAL",
            ano=ano,
            semestre="",
            tipo_aluno="normal",
        )
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

        response = self.ajax_post(
            REPORT_URL,
            data,
            referer=REPORT_URL,
        )
        self.save_debug("04_periodicidade_integral.xml", response)
        return response

    def abrir_dialogo_curso(self) -> requests.Response:
        self._say("[7/9] Abrindo diálogo de cursos do Stricto Sensu...")

        source = "form:consultaDadosCurso:consultaDadosCurso"

        response = self.ajax_post(
            REPORT_URL,
            self.click_payload(
                "form",
                source,
                self.form_principal(
                    unidade=STRICTO_UNIT_VALUE,
                    periodicidade="INTEGRAL",
                    tipo_aluno="normal",
                    cursos="",
                ),
            ),
            referer=REPORT_URL,
        )
        self.save_debug("05_dialogo_cursos.xml", response)
        return response

    @staticmethod
    def find_course_sources(
        response_text: str,
    ) -> list[tuple[str, str]]:
        """
        Procura linhas clicáveis no diálogo de cursos.

        Na captura, os dois cursos foram selecionados pelos componentes:
            formCurso:filtrosCurso:1:j_idt304
            formCurso:filtrosCurso:2:j_idt304
        """
        decoded = html.unescape(response_text)
        blocks = re.findall(
            r'<!\[CDATA\[(.*?)\]\]>',
            decoded,
            flags=re.I | re.S,
        ) or [decoded]

        found: list[tuple[str, str]] = []

        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")

            for row in soup.find_all("tr"):
                row_text = " ".join(row.stripped_strings).strip()
                if not row_text:
                    continue

                for element in row.find_all(
                    ["a", "button"],
                    attrs={"id": True},
                ):
                    element_id = str(element.get("id"))
                    onclick = str(element.get("onclick") or "")

                    if (
                        "formCurso:filtrosCurso:" in element_id
                        and "RichFaces.ajax" in onclick
                        and "tooltip" not in element_id.casefold()
                    ):
                        found.append((row_text, element_id))
                        break

        return found

    def selecionar_cursos_stricto(
        self,
        dialog_response: requests.Response,
    ) -> None:
        self._say("[8/9] Selecionando os dois cursos do Stricto Sensu...")

        rows = self.find_course_sources(dialog_response.text)

        if rows:
            self._say("          Opções detectadas no diálogo:")
            for text, _ in rows:
                self._say(f"          - {text}")

        used_sources: set[str] = set()

        for index, target_course in enumerate(STRICTO_COURSES, start=1):
            target_norm = normalize_text(target_course)

            candidates = [
                source
                for row_text, source in rows
                if target_norm in normalize_text(row_text)
                and source not in used_sources
            ]

            if candidates:
                source = candidates[0]
            else:
                # Fallback exatamente como a captura fornecida:
                # Ciência, Tecnologia e Educação -> índice 1
                # Saúde e Desigualdade Social -> índice 2
                source = (
                    f"formCurso:filtrosCurso:{index}:j_idt304"
                )

            self._say(f"          {target_course}")
            self._say(f"          -> JSF source: {source}")

            response = self.ajax_post(
                REPORT_URL,
                self.click_payload(
                    "formCurso",
                    source,
                    {
                        "formCurso:filtrosCurso:j_idt294": "",
                        "formCurso:filtrosCurso2:j_idt315": "",
                    },
                ),
                referer=REPORT_URL,
            )
            self.save_debug(
                f"06_curso_{index}_selecionado.xml",
                response,
            )

            used_sources.add(source)

            # A segunda seleção deve usar o estado devolvido pela primeira.
            # Se o HTML mudou e trouxer IDs novos, atualizamos as linhas.
            newer_rows = self.find_course_sources(response.text)
            if newer_rows:
                rows = newer_rows

    @staticmethod
    def extract_download_url(text: str) -> str | None:
        decoded = html.unescape(text)

        patterns = [
            (
                r'(https?://[^"\'<>\s\\]+/'
                r'DownloadRelatorioSV\?relatorio=[^"\'<>\s\\]+\.xlsx)'
            ),
            (
                r'(/DownloadRelatorioSV\?'
                r'relatorio=[^"\'<>\s\\]+\.xlsx)'
            ),
            (
                r'window\.open\(\s*["\']'
                r'([^"\']*DownloadRelatorioSV[^"\']+\.xlsx)["\']'
            ),
        ]

        for pattern in patterns:
            match = re.search(pattern, decoded, flags=re.I)
            if match:
                return html.unescape(match.group(1))

        return None

    def gerar_excel_sintetico(self, output: Path) -> Path:
        self._say("[9/9] Gerando Excel Sintético...")

        source = "form:imprimirExcelSintetico:imprimirExcelSintetico"

        response = self.ajax_post(
            REPORT_URL,
            self.click_payload(
                "form",
                source,
                self.form_principal(
                    unidade=STRICTO_UNIT_VALUE,
                    periodicidade="INTEGRAL",
                    tipo_aluno="normal",
                    cursos=STRICTO_COURSES_VALUE,
                ),
            ),
            referer=REPORT_URL,
        )
        self.save_debug("07_gerar_excel_sintetico.xml", response)

        download_url = self.extract_download_url(response.text)

        if not download_url:
            decoded = html.unescape(response.text)

            message = None
            match = re.search(
                r'class=["\'][^"\']*mensagemDetalhada[^"\']*["\']'
                r'[^>]*>(.*?)</span>',
                decoded,
                flags=re.I | re.S,
            )
            if match:
                message = re.sub(
                    r"<[^>]+>",
                    "",
                    match.group(1),
                ).strip()

            detail = f" Mensagem do SEI: {message}" if message else ""

            debug_hint = (
                f" Consulte {self.debug_dir / '07_gerar_excel_sintetico.xml'}."
                if self.debug_dir is not None
                else " A estrutura da tela do SEI pode ter mudado."
            )
            raise RuntimeError(
                "O POST imprimirExcelSintetico foi executado, "
                "mas a URL DownloadRelatorioSV não apareceu."
                + detail
                + debug_hint
            )

        absolute_url = urljoin(BASE, download_url)
        self._say("          Relatório integral gerado; iniciando download do XLSX.")

        response = self.session.get(
            absolute_url,
            headers={
                "Referer": REPORT_URL,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
            timeout=120,
        )
        response.raise_for_status()

        if not response.content.startswith(b"PK"):
            self.save_debug("download_nao_xlsx.bin", response)
            raise RuntimeError(
                "A resposta do DownloadRelatorioSV não parece ser XLSX."
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.content)
        return output



def download_stricto_integral_report(
    username: str,
    password: str,
    output: str | Path,
    *,
    year: str | int | None = None,
    debug_dir: str | Path | None = None,
    verbose: bool = False,
) -> Path:
    """Download the integral Stricto Sensu synthetic roster for both DM areas.

    Credentials live only in this call and are never written to disk. ``year`` is
    required by the legacy JSF event that changes SEMESTRAL to INTEGRAL; it does
    not turn the resulting report into an annual report.
    """
    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        raise ValueError("Usuário e senha do SEI são obrigatórios.")
    selected_year = str(year or __import__("datetime").date.today().year).strip()
    if not (selected_year.isdigit() and len(selected_year) == 4):
        raise ValueError("O ano técnico do evento do SEI deve possuir quatro dígitos.")
    destination = Path(output).expanduser().resolve()
    bot = SEIStrictoBot(
        debug_dir=Path(debug_dir) if debug_dir else None,
        verbose=verbose,
    )
    try:
        bot.login(username, password)
        bot.abrir_relatorio()
        dialog = bot.abrir_dialogo_unidade(selected_year)
        units = bot.preparar_lista_unidades(dialog)
        bot.selecionar_stricto(units)
        bot.mudar_para_integral(selected_year)
        course_dialog = bot.abrir_dialogo_curso()
        bot.selecionar_cursos_stricto(course_dialog)
        return bot.gerar_excel_sintetico(destination)
    finally:
        bot.session.close()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baixa o Excel Sintético do Stricto Sensu no SEI."
    )
    parser.add_argument(
        "--ano",
        default="2025",
        help=(
            "Ano enviado no evento que troca SEMESTRAL -> INTEGRAL. "
            "Na captura foi 2025."
        ),
    )
    parser.add_argument(
        "--saida",
        default=None,
        help="Caminho do XLSX. Padrão: mesma pasta do script.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 76)
    print("SEI/UNIVC - STRICTO SENSU - RELATÓRIO INTEGRAL")
    print("=" * 76)
    print(f"Unidade:      {STRICTO_UNIT_VALUE.strip()}")
    print("Periodicidade: INTEGRAL")
    print("Cursos:")
    for course in STRICTO_COURSES:
        print(f"  - {course}")
    print()

    username = input("Usuário SEI: ").strip()
    password = getpass.getpass("Senha SEI: ")

    if not username or not password:
        print("Usuário e senha são obrigatórios.")
        return 2

    output = (
        Path(args.saida).expanduser().resolve()
        if args.saida
        else SCRIPT_DIR / "stricto_sensu_integral.xlsx"
    )

    bot = SEIStrictoBot(debug_dir=DEBUG_DIR, verbose=True)

    try:
        bot.login(username, password)
        bot.abrir_relatorio()

        dialog = bot.abrir_dialogo_unidade(args.ano)
        units = bot.preparar_lista_unidades(dialog)
        bot.selecionar_stricto(units)

        bot.mudar_para_integral(args.ano)

        course_dialog = bot.abrir_dialogo_curso()
        bot.selecionar_cursos_stricto(course_dialog)

        result = bot.gerar_excel_sintetico(output)

        print()
        print("SUCESSO")
        print(f"Arquivo salvo em: {result}")
        return 0

    except Exception as exc:
        print()
        print(f"ERRO: {exc}")
        print(f"Debug salvo em: {DEBUG_DIR}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
