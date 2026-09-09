#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot de teste - SEI/UNIVC
Relatorio: Mapa de Nota do Aluno por Turma -> Excel

Este script faz o login no SEI com usuario e senha informados em tempo
de execucao, deixa o servidor criar o JSESSIONID automaticamente, percorre
as etapas JSF/RichFaces observadas no navegador e tenta baixar o XLSX gerado.

Dependencias:
    pip install requests beautifulsoup4

Uso:
    python sei_notas_administracao.py

Opcionalmente:
    python sei_notas_administracao.py --ano 2026 --semestre 1 --curso "Administração"

IMPORTANTE:
- Nao fixe usuario, senha, JSESSIONID ou javax.faces.ViewState no codigo.
- A senha e lida de forma oculta com getpass.
- O JSESSIONID e criado/gerenciado automaticamente pela requests.Session().
- Use apenas em uma conta/sessao que voce esta autorizado a acessar.
"""

from __future__ import annotations
import unicodedata

import argparse
import getpass
import html
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from academic_excel_parser import ler_registros

from academic_catalog import (
    COURSE_ALIASES,
    COURSE_SEARCH_TERMS,
    COURSE_SEI_FORM_VALUES,
    COURSE_SEI_TURN_PREFERENCES,
    DCS_COURSES,
    EDUCACAO_FISICA_COURSES,
    DTNH_COURSES,
    canonical_course_name,
    course_aliases,
    course_name_matches,
    normalize_course_text,
)


BASE = "https://sei.ivc.br"
SCRIPT_DIR = Path(__file__).resolve().parent
LOGIN_URL = f"{BASE}/index.xhtml"
HOME_URL = f"{BASE}/visaoAdministrativo/administrativo/homeAdministrador.xhtml"
REPORT_URL = (
    f"{BASE}/visaoAdministrativo/academico/relatorio/"
    "mapaNotaAlunoPorTurmaRel.xhtml"
)
MENU_JS_URL = f"{BASE}/javax.faces.resource/script/menuTopo.js.xhtml?ver=1.1"
KNOWLEDGE_URL = f"{BASE}/webservice/baseconhecimento/ativos"


class SEIBot:
    def __init__(self, debug_dir: Path = Path("debug_sei")) -> None:
        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:154.0) "
                    "Gecko/20100101 Firefox/154.0"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )

        self.viewstate: str | None = None
        # Snapshot do formulario principal devolvido pelo proprio SEI apos a
        # selecao do curso. O relatorio e JSF/RichFaces e parte do estado nao
        # esta representada apenas por form:nomeCurso/ViewState; por isso o
        # clique em imprimirExcel deve reaproveitar os controles reais que o
        # navegador recebeu, em vez de reconstruir o form manualmente.
        self._main_form_snapshot: dict[str, str] | None = None
        self.last_course_selection: dict[str, str | int] | None = None
        self.debug_dir = debug_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _extract_viewstate_from_html(text: str) -> str | None:
        soup = BeautifulSoup(text, "html.parser")
        el = soup.find("input", attrs={"name": "javax.faces.ViewState"})
        if el and el.get("value"):
            return html.unescape(str(el["value"]))

        match = re.search(
            r'name=["\']javax\.faces\.ViewState["\'][^>]*'
            r'value=["\']([^"\']+)["\']',
            text,
            flags=re.I,
        )
        if match:
            return html.unescape(match.group(1))
        return None

    @staticmethod
    def _extract_viewstate_from_partial(text: str) -> str | None:
        # RichFaces pode devolver IDs como:
        #   javax.faces.ViewState
        #   j_id1:javax.faces.ViewState:0
        patterns = [
            (
                r'<update[^>]+id=["\'][^"\']*javax\.faces\.ViewState[^"\']*["\'][^>]*>'
                r'\s*<!\[CDATA\[(.*?)\]\]>\s*</update>'
            ),
            (
                r'<update[^>]+id=["\'][^"\']*javax\.faces\.ViewState[^"\']*["\'][^>]*>'
                r'(.*?)</update>'
            ),
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                return html.unescape(match.group(1).strip())
        return None

    @staticmethod
    def _extract_form_snapshot_from_partial(
        text: str,
        *,
        form_id: str = "form",
    ) -> dict[str, str] | None:
        """Serializa os controles do formulario HTML devolvido pelo RichFaces.

        O navegador envia os valores *atuais* do form no clique seguinte. Em
        paginas JSF antigas esses valores podem variar conforme curso, periodo e
        configuracao academica. Reconstruir o payload com uma lista hardcoded
        funciona apenas enquanto o formulario coincide exatamente com a captura.
        """
        decoded = html.unescape(text)
        blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', decoded, flags=re.I | re.S)
        if not blocks:
            blocks = [decoded]

        form = None
        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")
            form = soup.find("form", attrs={"id": form_id}) or soup.find(
                "form", attrs={"name": form_id}
            )
            if form is not None:
                break
        if form is None:
            return None

        payload: dict[str, str] = {}
        for control in form.find_all(["input", "select", "textarea"]):
            if control.has_attr("disabled"):
                continue
            name = str(control.get("name") or "").strip()
            if not name:
                continue
            tag = control.name.casefold()
            if tag == "input":
                input_type = str(control.get("type") or "text").casefold()
                if input_type in {"button", "submit", "reset", "image", "file"}:
                    continue
                if input_type in {"checkbox", "radio"}:
                    if not control.has_attr("checked"):
                        continue
                    # HTML envia "on" quando checkbox/radio marcado nao possui
                    # atributo value explicito. E exatamente o que aparece no HAR.
                    raw_value = control.get("value")
                    payload[name] = html.unescape(
                        str(raw_value if raw_value is not None else "on")
                    )
                    continue
                payload[name] = html.unescape(str(control.get("value") or ""))
            elif tag == "select":
                options = control.find_all("option")
                selected = [option for option in options if option.has_attr("selected")]
                option = selected[0] if selected else (options[0] if options else None)
                payload[name] = (
                    html.unescape(str(option.get("value") or "")) if option is not None else ""
                )
            else:
                payload[name] = html.unescape(control.get_text())
        return payload

    def _excel_click_payload(
        self,
        *,
        ano: str,
        semestre: str,
        course_name: str,
    ) -> dict[str, str]:
        """Monta o POST de imprimirExcel a partir do form real do SEI.

        Se o partial-response de selecao nao trouxer o formulario principal,
        mantemos o payload legado como fallback. Quando ha snapshot, validamos
        periodo e curso antes do POST para impedir download silencioso de outro
        contexto do backing bean.
        """
        source = "form:imprimirExcel:imprimirExcel"
        snapshot = dict(self._main_form_snapshot or {})
        if snapshot:
            selected_year = str(snapshot.get("form:anoRegistroFalta") or "").strip()
            selected_semester = str(snapshot.get("form:registroFaltaSemestre") or "").strip()
            selected_course = str(snapshot.get("form:nomeCurso") or "").strip()

            if selected_year and selected_year != str(ano):
                raise RuntimeError(
                    "O formulario devolvido pelo SEI ficou em outro ano antes do Excel: "
                    f"esperado {ano}, recebido {selected_year}."
                )
            if selected_semester and selected_semester != str(semestre):
                raise RuntimeError(
                    "O formulario devolvido pelo SEI ficou em outro semestre antes do Excel: "
                    f"esperado {semestre}, recebido {selected_semester}."
                )
            if selected_course and not course_name_matches(selected_course, course_name):
                raise RuntimeError(
                    "O formulario devolvido pelo SEI ficou em outro curso antes do Excel: "
                    f"esperado {course_name!r}, recebido {selected_course!r}."
                )

            # Event fields sao adicionados por ultimo, como o RichFaces faz no
            # clique. O ViewState real mais recente e injetado por ajax_post().
            payload = snapshot
            payload.update(self.click_payload("form", source))
            return payload

        return self.click_payload(
            "form",
            source,
            extra=self.base_form(
                ano=ano,
                semestre=semestre,
                curso=course_name,
                layout="MapaNotaAlunoPorTurmaRel_unidadeTurmaDiscSala",
            ),
        )

    def _update_viewstate(self, response: requests.Response) -> None:
        content_type = response.headers.get("Content-Type", "").lower()
        if not any(x in content_type for x in ("text", "html", "xml")):
            return
        new_state = (
            self._extract_viewstate_from_partial(response.text)
            or self._extract_viewstate_from_html(response.text)
        )
        if new_state:
            self.viewstate = new_state

    def _save_debug(self, name: str, response: requests.Response) -> Path:
        path = self.debug_dir / name
        path.write_bytes(response.content)
        return path

    def _assert_not_logged_out(self, response: requests.Response) -> None:
        text = response.text.lower()
        if "form:usuario" in text and "form:senha" in text:
            path = self._save_debug("sessao_expirada.html", response)
            raise RuntimeError(
                "A sessao parece ter expirado ou o JSESSIONID nao e valido. "
                f"Resposta salva em {path}"
            )

    def get_html(
        self,
        url: str,
        *,
        referer: str | None = None,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        }
        if referer:
            headers["Referer"] = referer

        response = self.session.get(
            url,
            headers=headers,
            params=params,
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()
        self._assert_not_logged_out(response)
        self._update_viewstate(response)
        return response

    def get_resource(
        self,
        url: str,
        *,
        referer: str,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        response = self.session.get(
            url,
            headers={
                "Accept": "*/*",
                "Referer": referer,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        self._update_viewstate(response)
        return response

    def ajax_post(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str,
    ) -> requests.Response:
        if not self.viewstate:
            raise RuntimeError(
                "Nao ha javax.faces.ViewState carregado. "
                "Abra a pagina correspondente antes do POST."
            )

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
            timeout=60,
        )
        response.raise_for_status()
        self._assert_not_logged_out(response)
        self._update_viewstate(response)
        return response

    @staticmethod
    def click_payload(
        form: str,
        source: str,
        *,
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

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_jsf_redirect(text: str) -> str | None:
        """Extrai <redirect url="..."> de uma resposta partial-response do JSF."""
        match = re.search(
            r'<redirect\s+url=["\']([^"\']+)["\']',
            text,
            flags=re.I,
        )
        if match:
            return html.unescape(match.group(1))
        return None

    def _login_ajax_post(
        self,
        data: dict[str, str],
    ) -> requests.Response:
        """
        POST AJAX usado especificamente durante o login.

        Nao usa _assert_not_logged_out(), porque durante o proprio processo
        de login a resposta pode legitimamente conter componentes da tela
        de autenticacao.
        """
        if not self.viewstate:
            raise RuntimeError(
                "Nao ha javax.faces.ViewState carregado para executar o login."
            )

        payload = dict(data)
        payload["javax.faces.ViewState"] = self.viewstate

        response = self.session.post(
            LOGIN_URL,
            headers={
                "Accept": "*/*",
                "Faces-Request": "partial/ajax",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": BASE,
                "Referer": LOGIN_URL,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            data=payload,
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()
        self._update_viewstate(response)
        return response

    def login(self, username: str, password: str) -> None:
        """
        Reproduz as tres requisicoes de login capturadas:
        1) loginBtn com usuario/senha
        2) renderFormPerfil
        3) logarDiretamenteComoFuncionario
        """
        print("[LOGIN 1/4] Abrindo pagina de login...")

        response = self.session.get(
            LOGIN_URL,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()
        self._update_viewstate(response)

        if not self.viewstate:
            path = self._save_debug("login_inicial_sem_viewstate.html", response)
            raise RuntimeError(
                "Nao encontrei javax.faces.ViewState na pagina inicial. "
                f"Resposta salva em {path}"
            )

        print("[LOGIN 2/4] Enviando usuario e senha...")

        source = "form:loginBtn:loginBtn"
        response = self._login_ajax_post(
            self.click_payload(
                "form",
                source,
                extra={
                    "form:usuario": username,
                    "form:senha": password,
                },
            )
        )
        self._save_debug("login_1_credenciais.xml", response)

        # Se houver mensagem de erro comum na resposta, falha cedo.
        low = html.unescape(response.text).lower()
        erros_comuns = (
            "senha incorreta",
            "usuário ou senha",
            "usuario ou senha",
            "login inválido",
            "login invalido",
            "credenciais inválidas",
            "credenciais invalidas",
        )
        if any(msg in low for msg in erros_comuns):
            raise RuntimeError(
                "O SEI parece ter rejeitado usuario/senha. "
                "Veja debug_sei/login_1_credenciais.xml"
            )

        print("[LOGIN 3/4] Renderizando perfil...")

        source = "formPerfil:renderFormPerfil:renderFormPerfil"
        response = self._login_ajax_post(
            self.click_payload(
                "formPerfil",
                source,
                extra={"org.richfaces.focus": ""},
            )
        )
        self._save_debug("login_2_perfil.xml", response)

        print("[LOGIN 4/4] Entrando como funcionario...")

        source = (
            "formPerfil:logarDiretamenteComoFuncionario:"
            "logarDiretamenteComoFuncionario"
        )
        response = self._login_ajax_post(
            self.click_payload(
                "formPerfil",
                source,
                extra={"org.richfaces.focus": ""},
            )
        )
        self._save_debug("login_3_funcionario.xml", response)

        redirect = self._extract_jsf_redirect(response.text)
        if redirect:
            target = urljoin(BASE, redirect)
            print(f"       Redirect JSF detectado: {target}")
            response = self.session.get(
                target,
                headers={"Referer": LOGIN_URL},
                timeout=60,
                allow_redirects=True,
            )
            response.raise_for_status()
            self._update_viewstate(response)

        # Confirma a sessao acessando a home administrativa.
        response = self.session.get(
            HOME_URL,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Referer": LOGIN_URL,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            },
            timeout=60,
            allow_redirects=True,
        )
        response.raise_for_status()

        final_url = response.url.lower()
        body = response.text.lower()

        if (
            "index.xhtml" in final_url
            or ("form:usuario" in body and "form:senha" in body)
        ):
            path = self._save_debug("login_nao_confirmado.html", response)
            raise RuntimeError(
                "As tres etapas foram enviadas, mas a sessao administrativa "
                "nao foi confirmada. "
                f"Resposta salva em {path}"
            )

        self._update_viewstate(response)

        jsessionid = self.session.cookies.get("JSESSIONID")
        if jsessionid:
            print("       Login confirmado; JSESSIONID obtido automaticamente.")
        else:
            print(
                "       Home administrativa acessada. "
                "O cookie de sessao foi gerenciado pela Session."
            )

    def abrir_home(self) -> None:
        print("[1/10] Abrindo home administrativa e obtendo ViewState...")
        response = self.get_html(HOME_URL)
        if not self.viewstate:
            path = self._save_debug("home_sem_viewstate.html", response)
            raise RuntimeError(f"Nao encontrei ViewState na home. Resposta: {path}")
        print(f"       ViewState HOME: {self.viewstate[:24]}...")

    def abrir_menu_academico(self) -> None:
        print("[2/10] Acionando menu Academico...")
        source = "menuAcad"
        data = self.click_payload("formMenuLateral", source)
        self.ajax_post(HOME_URL, data, referer=HOME_URL)

    def carregar_menu_js(self) -> None:
        print("[3/10] Carregando menuTopo.js.xhtml...")
        self.get_resource(MENU_JS_URL, referer=HOME_URL)

    def abrir_relatorio(self) -> None:
        print("[4/10] Abrindo mapaNotaAlunoPorTurmaRel.xhtml...")
        self._main_form_snapshot = None
        response = self.get_html(REPORT_URL, referer=HOME_URL)
        if not self.viewstate:
            path = self._save_debug("relatorio_sem_viewstate.html", response)
            raise RuntimeError(f"Nao encontrei ViewState do relatorio. Resposta: {path}")
        print(f"       ViewState RELATORIO: {self.viewstate[:24]}...")

    def carregar_base_conhecimento(self) -> None:
        print("[5/10] Chamando baseconhecimento/ativos...")
        self.get_resource(
            KNOWLEDGE_URL,
            referer=REPORT_URL,
            params={"rota": "/mapaNotaAlunoPorTurmaRel.xhtml"},
        )

    def inicializar_estado_relatorio_educacao_fisica(self, *, ano: str, semestre: str) -> bool:
        """Reproduz o clique de inicialização observado nos HARs reais.

        Nos dois HARs manuais de Educação Física há um POST anterior à seleção
        de unidade/curso com source ``form:j_idt477``. Os demais cursos já
        funcionam sem essa etapa, então ela é aplicada somente às duas
        habilitações de Educação Física para não alterar o fluxo estável.

        O identificador é legado/dinâmico; por segurança, uma falha nessa etapa
        é registrada e o fluxo continua usando as etapas já comprovadas.
        """
        print("[5.1/10] Inicializando estado do relatório para Educação Física...")
        source = "form:j_idt477"
        data = self.base_form(ano=ano, semestre=semestre)
        # O HAR mais completo executa a inicialização antes de escolher a unidade.
        data["form:listaUnidadeEnsino"] = "0"
        data.update({
            "javax.faces.source": source,
            "javax.faces.partial.event": "click",
            "javax.faces.partial.execute": f"{source} @component",
            "javax.faces.partial.render": "@component",
            "javax.faces.behavior.event": "click",
            "org.richfaces.ajax.component": source,
            "rfExt": "null",
            "AJAX:EVENTS_COUNT": "1",
            "javax.faces.partial.ajax": "true",
        })
        try:
            response = self.ajax_post(REPORT_URL, data, referer=REPORT_URL)
            self._save_debug("resposta_inicializacao_edfisica.xml", response)
        except Exception as exc:
            print(
                "       Aviso: a inicialização adicional de Educação Física falhou "
                f"({exc}); seguindo com o fluxo padrão."
            )
            return False
        ok = bool(re.search(r'<update[^>]+id=["\']form["\']', response.text, flags=re.I))
        print(f"       Inicialização adicional {'confirmada' if ok else 'não confirmada'} pelo RichFaces.")
        return ok

    @staticmethod
    def base_form(
        *,
        ano: str,
        semestre: str,
        curso: str = "",
        layout: str = "MapaNotaAlunoPorTurmaRel_unidadeTurmaDiscSala",
    ) -> dict[str, str]:
        return {
            "form": "form",
            "form:tipoCurso": "SE",
            "form:listaUnidadeEnsino": "2",
            "form:anoRegistroFalta": ano,
            "form:registroFaltaSemestre": semestre,
            "form:dataInicioPeriodo:dataInicioPeriodo": "",
            "form:dataFimPeriodo:dataFimPeriodo": "",
            "form:nomeTurno": "",
            "form:nomeCurso": curso,
            "form:turma": "",
            "form:disciplina": "",
            "form:configuracaoAcademico": "0",
            "form:sala": " - ",
            "form:professor": "",
            "form:tipoAluno": "todos",
            "form:tipoDisciplina": "ambas",
            "form:ordenarPor": "disciplina",
            "form:tipoLayout": layout,
            "form:funcionarioMatriculaPrincipal": "",
            "form:funcionarioNomePrincipal": "",
            "form:funcionarioMatriculaSecundario": "",
            "form:funcionarioNomeSecundario": "",
            "form:j_idt642:j_idt642": "on",
            "form:j_idt712:j_idt712": "on",
            "form:j_idt723:j_idt723": "on",
            "form:j_idt730:j_idt730": "on",
        }

    def selecionar_unidade(self, *, ano: str, semestre: str) -> None:
        print("[6/10] Disparando change da unidade de ensino...")
        source = "form:listaUnidadeEnsino"
        data = self.base_form(ano=ano, semestre=semestre)
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
        self.ajax_post(REPORT_URL, data, referer=REPORT_URL)

    def abrir_dialogo_curso(self, *, ano: str, semestre: str) -> None:
        print("[7/10] Abrindo dialogo de consulta de curso...")
        source = "form:consultaDadosCurso:consultaDadosCurso"
        data = self.click_payload(
            "form",
            source,
            extra=self.base_form(ano=ano, semestre=semestre),
        )
        self.ajax_post(REPORT_URL, data, referer=REPORT_URL)

    def pesquisar_curso(self, consulta: str) -> requests.Response:
        print(f"[8/10] Pesquisando curso: {consulta!r}...")
        source = "formCurso:btnConsultar:btnConsultar"
        data = self.click_payload(
            "formCurso",
            source,
            extra={
                "formCurso:consultaCurso": "nome",
                "formCurso:valorConsultaCurso": consulta,
            },
        )
        response = self.ajax_post(REPORT_URL, data, referer=REPORT_URL)
        self._save_debug("resultado_busca_curso.xml", response)
        return response

    @staticmethod
    def _course_scroller_source(response_text: str) -> str | None:
        decoded = html.unescape(response_text)
        match = re.search(
            r'id=["\']([^"\']*resultadoConsultaCurso:scResultadoCurso)["\']',
            decoded,
            flags=re.I,
        )
        return match.group(1) if match else None

    @staticmethod
    def _course_scroller_current_page(response_text: str) -> int:
        decoded = html.unescape(response_text)
        match = re.search(r'"currentPage"\s*:\s*(\d+)', decoded, flags=re.I)
        if match:
            return max(1, int(match.group(1)))
        match = re.search(r'scResultadoCurso_ds_(\d+)[^>]*rf-ds-act', decoded, flags=re.I)
        return max(1, int(match.group(1))) if match else 1

    @staticmethod
    def _course_scroller_has_next(response_text: str) -> bool:
        decoded = html.unescape(response_text).casefold()
        return "scresultadocurso_ds_next" in decoded

    def paginar_resultados_curso(
        self,
        *,
        search_term: str,
        page: int,
        response_text: str,
    ) -> requests.Response:
        """Avança o DataScroller RichFaces do diálogo de cursos.

        O componente é descoberto na resposta atual; nenhum j_idt dinâmico ou
        número de linha é fixado. O mesmo fluxo atende DTNH e DCS.
        """
        source = self._course_scroller_source(response_text)
        if not source:
            raise RuntimeError("O resultado de cursos não expôs um DataScroller paginável.")
        data = {
            "formCurso": "formCurso",
            "formCurso:consultaCurso": "nome",
            "formCurso:valorConsultaCurso": search_term,
            "javax.faces.source": source,
            "javax.faces.partial.event": "rich:datascroller:onscroll",
            "javax.faces.partial.execute": f"{source} @component",
            "javax.faces.partial.render": "@component",
            f"{source}:page": str(page),
            "org.richfaces.ajax.component": source,
            source: source,
            "rfExt": "null",
            "AJAX:EVENTS_COUNT": "1",
            "javax.faces.partial.ajax": "true",
        }
        response = self.ajax_post(REPORT_URL, data, referer=REPORT_URL)
        self._save_debug(f"resultado_busca_curso_pagina_{page}.xml", response)
        return response

    @staticmethod
    def encontrar_candidato_do_curso(
        response_text: str,
        course_name: str,
    ) -> tuple[str | None, str | None]:
        """Retorna (ação JSF de Selecionar, rótulo SEI) para o curso esperado.

        A identidade usa aliases explícitos e a ação é escolhida semanticamente
        pela coluna/opção "Selecionar", evitando confundir o link do nome do
        curso com o botão que realmente aplica a seleção.
        """
        decoded = html.unescape(response_text)
        aliases = course_aliases(course_name)
        normalized_aliases = [(normalize_course_text(a), a) for a in aliases]
        target_norm = normalize_course_text(course_name)
        preferred_turn = normalize_course_text(COURSE_SEI_TURN_PREFERENCES.get(course_name, ""))

        blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', decoded, flags=re.I | re.S)
        if not blocks:
            blocks = [decoded]

        def valid_id(value: str) -> bool:
            low = value.casefold()
            return (
                "formcurso:resultadoconsultacurso:" in low
                and "tooltip" not in low
                and not low.endswith(":content")
                and not low.endswith(":header")
                and not low.endswith(":body")
            )

        def action_for_row(row) -> str | None:
            cells = row.find_all("td")
            option_cell = cells[-1] if cells else row
            clickables = row.find_all(["a", "button"], attrs={"id": True})
            scored: list[tuple[int, int, str]] = []
            for order, el in enumerate(clickables):
                element_id = str(el.get("id"))
                if not valid_id(element_id):
                    continue
                onclick = str(el.get("onclick") or "")
                if "RichFaces.ajax" not in onclick:
                    continue
                score = 10
                if el in option_cell.find_all(["a", "button"], attrs={"id": True}):
                    score += 80
                own_text = normalize_course_text(" ".join(el.stripped_strings))
                if "selecionar" in own_text:
                    score += 120
                tooltip = row.find(id=re.compile(rf"^{re.escape(element_id)}tooltip", re.I))
                if tooltip and "selecionar" in normalize_course_text(" ".join(tooltip.stripped_strings)):
                    score += 180
                if element_id.split(":")[-1:] == element_id.split(":")[-2:-1]:
                    score += 20
                scored.append((score, order, element_id))
            if not scored:
                return None
            return max(scored, key=lambda item: (item[0], item[1]))[2]

        ead_markers = ("ead", "a distancia", "ensino a distancia", "online")
        inactive_markers = ("inativo", "desativado")
        candidates: list[tuple[int, int, str, str]] = []
        order = 0
        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")
            for row in soup.find_all("tr"):
                order += 1
                cells = row.find_all("td")
                if not cells:
                    continue
                course_label = " ".join(cells[0].stripped_strings).strip()
                course_norm = normalize_course_text(course_label)
                turn_label = " ".join(cells[1].stripped_strings).strip() if len(cells) > 1 else ""
                turn_norm = normalize_course_text(turn_label)
                row_norm = normalize_course_text(" ".join(row.stripped_strings))
                if not course_norm:
                    continue

                alias_hits = [(norm, label) for norm, label in normalized_aliases if norm and norm == course_norm]
                # Comunicação Social também aparece no SEI com o alias curto
                # "Publicidade e Propaganda"; ele já faz parte de course_aliases.
                if not alias_hits:
                    continue

                source = action_for_row(row)
                if not source:
                    continue

                score = 1000 + max((len(norm) for norm, _ in alias_hits), default=0)
                if target_norm == course_norm:
                    score += 200
                if "presencial" in row_norm:
                    score += 40
                # Educação Física possui mais de uma configuração ativa com o mesmo
                # rótulo de curso. O turno NÃO determina Bacharelado/Licenciatura; a
                # identidade vem do nome do curso (Bac./Lic.). A preferência de turno
                # serve apenas para escolher deterministicamente uma linha ativa, sem
                # hardcodar índice/j_idt.
                if preferred_turn and turn_norm == preferred_turn:
                    score += 600
                if any(marker in row_norm for marker in ead_markers):
                    score -= 1000
                if any(marker in row_norm for marker in inactive_markers):
                    score -= 250
                candidates.append((score, order, source, course_label or course_name))

        if candidates:
            _, _, source, matched_label = max(candidates, key=lambda item: (item[0], item[1]))
            return source, matched_label
        return None, None

    @staticmethod
    def encontrar_source_do_curso(response_text: str, course_name: str) -> str | None:
        source, _ = SEIBot.encontrar_candidato_do_curso(response_text, course_name)
        return source

    @staticmethod
    def descrever_opcao_curso(response_text: str, source: str) -> dict[str, str]:
        """Retorna os rótulos visíveis da linha JSF escolhida, para diagnóstico."""
        decoded = html.unescape(response_text)
        blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', decoded, flags=re.I | re.S) or [decoded]
        for block in blocks:
            soup = BeautifulSoup(block, "html.parser")
            element = soup.find(id=source)
            if element is None:
                continue
            row = element.find_parent("tr")
            if row is None:
                continue
            cells = row.find_all("td")
            return {
                "curso": " ".join(cells[0].stripped_strings).strip() if cells else "",
                "turno": " ".join(cells[1].stripped_strings).strip() if len(cells) > 1 else "",
                "source": source,
            }
        return {"curso": "", "turno": "", "source": source}

    @staticmethod
    def _extract_selected_course_from_partial(text: str) -> str | None:
        """
        Tenta ler o valor do campo principal form:nomeCurso na resposta
        apos clicar na linha do curso.
        """
        decoded = html.unescape(text)

        patterns = [
            r'id=["\']form:nomeCurso["\'][^>]*value=["\']([^"\']*)["\']',
            r'name=["\']form:nomeCurso["\'][^>]*value=["\']([^"\']*)["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, decoded, flags=re.I)
            if match:
                return html.unescape(match.group(1)).strip()

        return None

    def selecionar_curso(
        self,
        search_response: requests.Response,
        *,
        course_name: str,
        search_term: str,
        fallback_source: str | None = None,
    ) -> str:
        source, matched_label = self.encontrar_candidato_do_curso(search_response.text, course_name)

        if not source and fallback_source:
            print(
                "       Nao foi possivel detectar o componente dinamicamente; "
                f"usando fallback capturado: {fallback_source}"
            )
            source = fallback_source

        if not source:
            path = self.debug_dir / "resultado_busca_curso.xml"
            raise RuntimeError(
                "Nao consegui localizar o botao/link da linha do curso "
                f"{course_name!r}. Veja {path}"
            )

        if "tooltip" in source.casefold() or source.casefold().endswith(":content"):
            raise RuntimeError(
                "O componente detectado pertence ao tooltip, nao ao botao "
                f"de selecao: {source}"
            )

        option = self.descrever_opcao_curso(search_response.text, source)
        if course_name in EDUCACAO_FISICA_COURSES:
            expected_label = COURSE_SEI_FORM_VALUES[course_name]
            if normalize_course_text(option.get("curso", "")) != normalize_course_text(expected_label):
                raise RuntimeError(
                    "A linha escolhida no seletor do SEI não é a habilitação esperada de Educação Física: "
                    f"esperado {expected_label!r}, linha {option.get('curso')!r}."
                )
        self.last_course_selection = {
            "curso_solicitado": course_name,
            "curso_linha": option.get("curso", ""),
            "turno_linha": option.get("turno", ""),
            "source": source,
            "pagina": self._course_scroller_current_page(search_response.text),
        }
        print(
            "       Linha selecionada no SEI: "
            f"curso={option.get('curso')!r}, turno={option.get('turno')!r}, "
            f"página={self.last_course_selection['pagina']}, source={source!r}."
        )

        data = self.click_payload(
            "formCurso",
            source,
            extra={
                "formCurso:consultaCurso": "nome",
                "formCurso:valorConsultaCurso": search_term,
            },
        )

        response = self.ajax_post(REPORT_URL, data, referer=REPORT_URL)
        self._save_debug("resposta_selecao_curso.xml", response)

        self._main_form_snapshot = self._extract_form_snapshot_from_partial(response.text)
        if self._main_form_snapshot:
            snap_year = self._main_form_snapshot.get("form:anoRegistroFalta", "")
            snap_sem = self._main_form_snapshot.get("form:registroFaltaSemestre", "")
            snap_course = self._main_form_snapshot.get("form:nomeCurso", "")
            print(
                "       Estado real do formulario capturado: "
                f"ano={snap_year!r}, semestre={snap_sem!r}, curso={snap_course!r}."
            )
        else:
            print(
                "       Aviso: a resposta de selecao nao trouxe o formulario principal; "
                "o Excel usara o fallback legado."
            )

        selected = self._extract_selected_course_from_partial(response.text)
        if selected:
            print(f"       Curso aplicado pelo SEI: {selected}")

            if not course_name_matches(selected, course_name):
                raise RuntimeError(
                    "O SEI retornou um curso diferente do esperado: "
                    f"{selected!r}. Veja debug_sei/resposta_selecao_curso.xml"
                )
            return selected

        # Algumas respostas RichFaces não devolvem o campo form:nomeCurso.
        # Nesse caso usamos primeiro o valor de formulário conhecido do SEI e,
        # para os demais cursos, o rótulo identificado na linha selecionada.
        fallback_value = COURSE_SEI_FORM_VALUES.get(course_name) or matched_label or course_name
        print(
            "       Selecao enviada; a resposta nao exibiu explicitamente "
            f"o valor de form:nomeCurso. Usando no SEI: {fallback_value!r}."
        )
        return fallback_value

    def alterar_layout(self, *, ano: str, semestre: str, course_name: str) -> None:
        """Compatibilidade com o fluxo antigo sem emitir um AJAX extra.

        O HAR real mostra ``MapaNotaAlunoPorTurmaRel_unidadeTurmaDiscSala``
        já presente desde os POSTs de unidade/curso e segue diretamente para
        ``imprimirExcel`` após selecionar o curso. Reenviar um ``change`` de
        ``form:tipoLayout`` não faz parte do contrato observado e pode deixar o
        backing bean do RichFaces em um estado diferente do navegador.
        """
        print("[9/10] Layout do relatório já configurado no formulário; sem POST adicional.")
        return None

    @staticmethod
    def extrair_url_download(text: str) -> str | None:
        decoded = html.unescape(text)
        patterns = [
            r'(/DownloadRelatorioSV\?relatorio=[^"\'< >\s\\]+\.xlsx)'.replace("< >", "<>"),
            r'(https?://[^"\'< >\s\\]+/DownloadRelatorioSV\?relatorio=[^"\'< >\s\\]+\.xlsx)'.replace("< >", "<>"),
            r'window\.open\(\s*["\']([^"\']*DownloadRelatorioSV[^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, decoded, flags=re.I)
            if match:
                return html.unescape(match.group(1))
        return None

    def gerar_excel(
        self,
        *,
        ano: str,
        semestre: str,
        course_name: str,
        output: Path,
    ) -> Path:
        print("[10/10] Acionando imprimirExcel com o estado real do formulario...")
        data = self._excel_click_payload(
            ano=ano,
            semestre=semestre,
            course_name=course_name,
        )
        response = self.ajax_post(REPORT_URL, data, referer=REPORT_URL)
        self._save_debug("resposta_imprimir_excel.xml", response)

        download_url = self.extrair_url_download(response.text)
        if not download_url:
            decoded = html.unescape(response.text)
            message = None

            match = re.search(
                r'class=["\'][^"\']*mensagemDetalhada[^"\']*["\'][^>]*>'
                r'(.*?)</span>',
                decoded,
                flags=re.I | re.S,
            )
            if match:
                message = re.sub(r"<[^>]+>", "", match.group(1)).strip()

            extra = f" Mensagem do SEI: {message}" if message else ""

            raise RuntimeError(
                "O POST de imprimirExcel foi executado, mas nao encontrei "
                "a URL /DownloadRelatorioSV?...xlsx na resposta."
                + extra
                + f" Veja {self.debug_dir / 'resposta_imprimir_excel.xml'}"
            )

        download_url = urljoin(BASE, download_url)
        print(f"       Download detectado: {download_url}")

        download = self.session.get(
            download_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": REPORT_URL,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            },
            timeout=120,
            allow_redirects=True,
        )
        download.raise_for_status()

        if not download.content.startswith(b"PK"):
            content_type = download.headers.get("Content-Type", "")
            path = self._save_debug("download_nao_xlsx.bin", download)
            raise RuntimeError(
                "A URL de download respondeu, mas o conteudo nao parece XLSX. "
                f"Content-Type: {content_type!r}. Salvo em {path}"
            )

        output.write_bytes(download.content)
        return output




def _normalize_course_text(value: str) -> str:
    # Compatibilidade interna com versões anteriores e testes existentes.
    return normalize_course_text(value)


def course_search_terms(course_name: str) -> tuple[str, ...]:
    """Termos de busca em ordem de preferência, compartilhados por DTNH/DCS."""
    primary = COURSE_SEARCH_TERMS.get(course_name, course_name)
    if course_name == "Comunicação Social - Publicidade e Propaganda":
        return tuple(dict.fromkeys((
            primary,
            "publicidade e propaganda",
            course_name,
            "comunicação social publicidade",
        )))
    if course_name in {"Educação Física - Bacharelado", "Educação Física - Licenciatura"}:
        return tuple(dict.fromkeys((primary, "educação física", course_name)))
    return (primary,)


def pesquisar_curso_compativel(bot: "SEIBot", course_name: str) -> tuple[str, requests.Response]:
    """Pesquisa o curso em todas as páginas relevantes do diálogo RichFaces.

    A paginação é genérica: DTNH e DCS usam o mesmo caminho. O alvo nunca é
    selecionado por índice de linha, apenas por identidade/alias do curso.
    """
    attempts: list[str] = []
    for term in course_search_terms(course_name):
        attempts.append(term)
        response = bot.pesquisar_curso(term)

        # RichFaces pode preservar a página do DataScroller entre pesquisas
        # dentro da mesma sessão/backing bean. Isso acontece especialmente
        # quando um curso anterior (por exemplo, Educação Física - Bacharelado)
        # foi encontrado na página 2 e a próxima consulta procura um curso que
        # está na página 1 (Licenciatura). Sempre normalizamos a busca para a
        # primeira página antes de varrer os resultados. A regra é genérica e
        # atende tanto DTNH quanto DCS.
        current_page = SEIBot._course_scroller_current_page(response.text)
        if current_page > 1:
            paginator = getattr(bot, "paginar_resultados_curso", None)
            if callable(paginator) and SEIBot._course_scroller_source(response.text):
                response = paginator(
                    search_term=term,
                    page=1,
                    response_text=response.text,
                )

        visited_pages: set[int] = set()
        for _ in range(20):
            source, _ = bot.encontrar_candidato_do_curso(response.text, course_name)
            current_page = SEIBot._course_scroller_current_page(response.text)
            if source:
                if current_page > 1:
                    print(f"       Curso localizado na página {current_page} da busca.")
                if len(attempts) > 1:
                    print(f"       Curso localizado após tentativas: {attempts!r}")
                return term, response
            if current_page in visited_pages:
                break
            visited_pages.add(current_page)
            if not SEIBot._course_scroller_has_next(response.text):
                break
            paginator = getattr(bot, "paginar_resultados_curso", None)
            if not callable(paginator):
                break
            response = paginator(
                search_term=term,
                page=current_page + 1,
                response_text=response.text,
            )
    raise RuntimeError(
        f"Não encontrei o curso {course_name!r} no diálogo do SEI. "
        f"Termos tentados: {attempts!r}. Veja debug_sei/resultado_busca_curso*.xml"
    )

def validar_xlsx_baixado(
    file_path: Path,
    *,
    course_name: str,
    ano: str,
    semestre: str,
) -> dict[str, object]:
    """Valida o XLSX imediatamente após o download, antes do repositório.

    Essa checagem separa falhas de seleção/estado JSF de falhas de importação.
    Para Educação Física, curso é definido exclusivamente pelo campo Curso: do
    relatório; EFB/EFL no nome da turma não participam da identidade.
    """
    metadata, registros, warnings = ler_registros(file_path)
    raw_course = str(metadata.get("curso") or "").strip()
    if not raw_course:
        raise RuntimeError("O XLSX baixado não informa o campo Curso:.")
    if not course_name_matches(raw_course, course_name):
        raise RuntimeError(
            "O XLSX baixado pertence a outro curso: "
            f"solicitado {course_name!r}, XLSX {raw_course!r}."
        )
    got_year = str(metadata.get("ano") or "").strip()
    got_semester = str(metadata.get("semestre") or "").strip()
    if got_year != str(ano) or got_semester != str(semestre):
        raise RuntimeError(
            "O XLSX baixado pertence a outro período: "
            f"solicitado {ano}/{semestre}, XLSX {got_year or '?'} / {got_semester or '?'} ."
        )
    return {
        "curso": raw_course,
        "ano": got_year,
        "semestre": got_semester,
        "registros": len(registros),
        "avisos": len(warnings),
    }


def safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_name = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name)
    return ascii_name.strip("_")


def ask_period(default_year: str = "2026", default_semester: str = "1") -> tuple[str, str]:
    year = input(f"Ano [{default_year}]: ").strip() or default_year

    while True:
        semester = input(f"Semestre (1 ou 2) [{default_semester}]: ").strip() or default_semester
        if semester in {"1", "2"}:
            return year, semester
        print("Informe 1 ou 2.")


def preparar_relatorio_para_curso(
    bot: "SEIBot",
    *,
    ano: str,
    semestre: str,
    course_name: str | None = None,
) -> None:
    """
    Reabre a tela do relatorio para limpar o estado do curso anterior e
    reproduz as etapas iniciais antes de cada nova consulta.
    """
    bot.abrir_relatorio()
    bot.carregar_base_conhecimento()
    if course_name in EDUCACAO_FISICA_COURSES:
        bot.inicializar_estado_relatorio_educacao_fisica(ano=ano, semestre=semestre)
    bot.selecionar_unidade(
        ano=ano,
        semestre=semestre,
    )
    bot.abrir_dialogo_curso(
        ano=ano,
        semestre=semestre,
    )


def baixar_todos_cursos_dtnh(
    bot: "SEIBot",
    *,
    ano: str,
    semestre: str,
    output_dir: Path,
) -> tuple[list[Path], list[tuple[str, str]]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    successes: list[Path] = []
    failures: list[tuple[str, str]] = []

    total = len(DTNH_COURSES)

    for index, course_name in enumerate(DTNH_COURSES, start=1):
        print()
        print("=" * 72)
        print(f"[CURSO {index}/{total}] {course_name}")
        print("=" * 72)

        try:
            preparar_relatorio_para_curso(
                bot,
                ano=ano,
                semestre=semestre,
                course_name=course_name,
            )

            search_term, search_response = pesquisar_curso_compativel(bot, course_name)

            sei_course_name = bot.selecionar_curso(
                search_response,
                course_name=course_name,
                search_term=search_term,
                fallback_source=None,
            )
            if sei_course_name != course_name:
                print(
                    f"       Rótulo efetivamente aplicado no SEI: {sei_course_name!r}. "
                    f"O Data UNIVC continuará salvando o curso como {course_name!r}."
                )

            # Depois do clique, o campo form:nomeCurso deve ser reenviado com o
            # valor que o próprio SEI aceitou. Usar aqui o nome institucional
            # completo fazia Comunicação Social falhar mesmo após a linha correta
            # ter sido selecionada.
            bot.alterar_layout(
                ano=ano,
                semestre=semestre,
                course_name=sei_course_name,
            )

            filename = (
                f"{safe_filename(course_name)}_{ano}_{semestre}.xlsx"
            )
            output = output_dir / filename

            result = bot.gerar_excel(
                ano=ano,
                semestre=semestre,
                course_name=sei_course_name,
                output=output,
            )

            successes.append(result)
            print(f"[OK] {course_name} -> {result}")

        except Exception as exc:
            failures.append((course_name, str(exc)))
            print(f"[FALHOU] {course_name}: {exc}")
            print("Continuando para o proximo curso...")

    return successes, failures

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bot para baixar os mapas de notas dos cursos do DTNH no SEI/UNIVC."
        )
    )

    parser.add_argument(
        "--ano",
        default=None,
        help="Ano academico. Se omitido, sera perguntado no inicio.",
    )
    parser.add_argument(
        "--semestre",
        choices=["1", "2"],
        default=None,
        help="Semestre. Se omitido, sera perguntado no inicio.",
    )
    parser.add_argument(
        "--saida",
        default=None,
        help=(
            "Pasta de saida. Se omitida, cria uma pasta ao lado do script "
            "com o nome notas_DTNH_ANO_SEMESTRE."
        ),
    )

    return parser.parse_args()

def main() -> int:
    args = parse_args()

    print("=" * 72)
    print("SEI/UNIVC - DTNH - MAPA DE NOTAS POR CURSO")
    print("=" * 72)
    print()

    if args.ano and args.semestre:
        ano = args.ano
        semestre = args.semestre
    else:
        ano, semestre = ask_period(
            default_year=args.ano or "2026",
            default_semester=args.semestre or "1",
        )

    if args.saida:
        output_dir = Path(args.saida).expanduser().resolve()
    else:
        output_dir = SCRIPT_DIR / f"notas_DTNH_{ano}_{semestre}"

    print()
    print(f"Periodo escolhido: {ano}/{semestre}")
    print(f"Pasta de saida:    {output_dir}")
    print()
    print("Cursos:")
    for course in DTNH_COURSES:
        print(f"  - {course}")
    print()

    username = input("Usuario SEI: ").strip()
    password = getpass.getpass("Senha SEI: ")

    if not username or not password:
        print("Usuario e senha sao obrigatorios.")
        return 2

    bot = SEIBot()

    try:
        bot.login(username, password)

        # Fazemos a abertura do menu academico uma unica vez.
        bot.abrir_home()
        bot.abrir_menu_academico()
        bot.carregar_menu_js()

        successes, failures = baixar_todos_cursos_dtnh(
            bot,
            ano=ano,
            semestre=semestre,
            output_dir=output_dir,
        )

        print()
        print("=" * 72)
        print("RESUMO")
        print("=" * 72)
        print(f"Arquivos baixados: {len(successes)}/{len(DTNH_COURSES)}")

        if successes:
            print()
            print("Sucessos:")
            for path in successes:
                print(f"  - {path.name}")

        if failures:
            print()
            print("Falhas:")
            for course_name, error in failures:
                print(f"  - {course_name}: {error}")

        print()
        print(f"Arquivos salvos em: {output_dir}")
        return 0 if not failures else 1

    except requests.RequestException as exc:
        print(f"\nERRO HTTP: {exc}")
        return 1
    except Exception as exc:
        print(f"\nERRO: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------
# Integração reutilizável pelo Data UNIVC v0.5.0
# ---------------------------------------------------------------------------
def baixar_cursos_sei(
    bot: "SEIBot",
    *,
    ano: str,
    semestre: str,
    output_dir: Path,
    cursos: list[str],
) -> tuple[list[tuple[str, Path]], list[tuple[str, str]]]:
    """Baixa o Mapa de Nota do Aluno por Turma para uma lista explícita de cursos.

    Esta função reaproveita exatamente o fluxo JSF/RichFaces já validado pelo script
    original e permite que o Data UNIVC escolha quais cursos consultar. Quando um
    curso não possui termo específico em ``COURSE_SEARCH_TERMS``, o próprio nome é
    usado como busca, o que também permite testar cursos de outras diretorias.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    successes: list[tuple[str, Path]] = []
    failures: list[tuple[str, str]] = []

    for course_name in cursos:
        course_name = str(course_name or "").strip()
        if not course_name:
            continue

        # Educação Física é o único caso com duas habilitações homônimas no mesmo
        # diálogo e múltiplas configurações/turnos. Fazemos até duas tentativas
        # completamente frescas caso o XLSX pós-download revele estado cruzado.
        max_attempts = 2 if course_name in EDUCACAO_FISICA_COURSES else 1
        last_error: Exception | None = None
        last_stage = "preparar relatório"

        for attempt in range(1, max_attempts + 1):
            stage = "preparar relatório"
            try:
                preparar_relatorio_para_curso(bot, ano=ano, semestre=semestre, course_name=course_name)
                stage = "buscar curso"
                search_term, search_response = pesquisar_curso_compativel(bot, course_name)
                stage = "selecionar curso"
                sei_course_name = bot.selecionar_curso(
                    search_response,
                    course_name=course_name,
                    search_term=search_term,
                    fallback_source=None,
                )
                if sei_course_name != course_name:
                    print(
                        f"       Rótulo efetivamente aplicado no SEI: {sei_course_name!r}. "
                        f"O Data UNIVC continuará salvando o curso como {course_name!r}."
                    )
                stage = "configurar relatório"
                bot.alterar_layout(ano=ano, semestre=semestre, course_name=sei_course_name)
                output = output_dir / f"{safe_filename(course_name)}_{ano}_{semestre}.xlsx"
                stage = "gerar/baixar Excel"
                result = bot.gerar_excel(
                    ano=ano,
                    semestre=semestre,
                    course_name=sei_course_name,
                    output=output,
                )

                if course_name in EDUCACAO_FISICA_COURSES:
                    stage = "validar XLSX baixado"
                    diagnostic = validar_xlsx_baixado(
                        result,
                        course_name=course_name,
                        ano=ano,
                        semestre=semestre,
                    )
                    print(
                        "       XLSX de Educação Física validado antes da importação: "
                        f"curso={diagnostic['curso']!r}, período={diagnostic['ano']}/{diagnostic['semestre']}, "
                        f"registros={diagnostic['registros']}."
                    )
                successes.append((course_name, result))
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                last_stage = stage
                if attempt < max_attempts:
                    print(
                        f"       Tentativa {attempt}/{max_attempts} falhou em {stage}: {exc}. "
                        "Reabrindo o relatório e repetindo Educação Física do zero."
                    )
                    continue
                break

        if last_error is not None:
            failures.append((course_name, f"{last_stage}: {last_error}"))

    return successes, failures
