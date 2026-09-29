from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class RepositoryError(RuntimeError):
    pass


class ValidationError(RepositoryError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


@dataclass(frozen=True)
class DatasetSchema:
    key: str
    label: str
    fields: tuple[str, ...]
    unique_fields: tuple[str, ...]
    template_headers: tuple[str, ...]


DATASETS: dict[str, DatasetSchema] = {
    "nps": DatasetSchema(
        key="nps", label="NPS do Curso",
        fields=("periodo", "curso", "respondentes", "promotores", "neutros", "detratores"),
        unique_fields=("periodo", "curso"),
        template_headers=("Período", "Curso", "Respondentes", "Promotores (9-10)", "Neutros (7-8)", "Detratores (0-6)"),
    ),
    "avaliacao_docente": DatasetSchema(
        key="avaliacao_docente", label="Avaliação Docente pelo Aluno",
        fields=("periodo", "curso", "disciplina", "professor", "respondentes", "nota_media"),
        unique_fields=("periodo", "curso", "disciplina", "professor"),
        template_headers=("Período", "Curso", "Disciplina", "Professor", "Respondentes", "Nota Média (0-10)"),
    ),
    "resultados": DatasetSchema(
        key="resultados", label="Resultados Acadêmicos",
        fields=("periodo", "curso", "disciplina", "turma", "matricula", "aluno", "media", "situacao", "aprovado", "motivo_reprovacao"),
        unique_fields=("periodo", "curso", "disciplina", "turma", "matricula"),
        template_headers=("Período", "Curso", "Disciplina", "Turma", "Matrícula", "Aluno", "Média", "Situação", "Aprovado", "Motivo da Reprovação"),
    ),
    "matriculas": DatasetSchema(
        key="matriculas", label="Matrículas Ativas",
        fields=("periodo", "curso", "matriculas"),
        unique_fields=("periodo", "curso"),
        template_headers=("Período", "Curso", "Matrículas Ativas"),
    ),
    "frequencia": DatasetSchema(
        key="frequencia", label="Frequência Média",
        fields=("periodo", "curso", "disciplina", "presencas_previstas", "presencas_registradas"),
        unique_fields=("periodo", "curso", "disciplina"),
        template_headers=("Período", "Curso", "Disciplina", "Presenças Previstas", "Presenças Registradas"),
    ),
}

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SEMESTER_RE = re.compile(r"^\d{4}-SEM[12]$")

HEADER_ALIASES = {
    "nps": {
        "periodo": {"periodo", "mes", "competencia"},
        "curso": {"curso"},
        "respondentes": {"respondentes", "total de respondentes"},
        "promotores": {"promotores", "promotores 9 10"},
        "neutros": {"neutros", "neutros 7 8"},
        "detratores": {"detratores", "detratores 0 6"},
    },
    "avaliacao_docente": {
        "periodo": {"periodo", "semestre", "competencia"},
        "curso": {"curso"},
        "disciplina": {"disciplina", "nome da disciplina"},
        "professor": {"professor", "docente", "nome do professor"},
        "respondentes": {"respondentes", "total de respondentes"},
        "nota_media": {"nota media", "media", "avaliacao media", "nota media 0 10"},
    },
    "resultados": {
        "periodo": {"periodo", "semestre", "competencia", "ano semestre"},
        "curso": {"curso"},
        "disciplina": {"disciplina", "nome da disciplina"},
        "turma": {"turma"},
        "matricula": {"matricula", "matricula aluno"},
        "aluno": {"aluno", "nome", "nome do aluno"},
        "media": {"media", "media final", "nota", "nota final"},
        "situacao": {"situacao", "status", "situacao oficial"},
        "aprovado": {"aprovado", "aprovacao"},
        "motivo_reprovacao": {"motivo da reprovacao", "motivo reprovacao", "motivo"},
    },
    "matriculas": {
        "periodo": {"periodo", "mes", "competencia"},
        "curso": {"curso"},
        "matriculas": {"matriculas", "matriculas ativas", "alunos ativos"},
    },
    "frequencia": {
        "periodo": {"periodo", "mes", "competencia"},
        "curso": {"curso"},
        "disciplina": {"disciplina", "aula"},
        "presencas_previstas": {"presencas previstas", "presencas possiveis", "aulas previstas"},
        "presencas_registradas": {"presencas registradas", "presencas", "presencas realizadas"},
    },
}


DISCIPLINE_HEADER_ALIASES = {
    "curso": {"curso"},
    "disciplina": {"disciplina", "nome da disciplina"},
    "ativo": {"ativo", "status"},
    "vigencia_inicio": {"vigencia inicio", "inicio da vigencia", "vigencia inicial"},
    "vigencia_fim": {"vigencia fim", "fim da vigencia", "vigencia final"},
    "recorte_metas": {"recorte para metas", "recorte metas", "recorte"},
}

def norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    repl = str.maketrans("áàãâéêíóôõúüç", "aaaaeeiooouuc")
    text = text.translate(repl)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

# KPIs that already have a data-entry/calculation flow implemented in the application.
# The institutional catalog can contain more indicators than the UI currently operationalizes.
ACADEMIC_DIRECTORATES: tuple[str, ...] = ("DTNH", "DCS", "DEAD")
ACADEMIC_UI_DATASETS: tuple[str, ...] = ("resultados",)

IMPLEMENTED_KPIS: dict[str, tuple[str, ...]] = {
    "DTNH": ("DTNH-01A", "DTNH-01B", "DTNH-01C", "DTNH-02", "DTNH-03"),
    "DCS": ("DCS-01A", "DCS-01B", "DCS-01C", "DCS-02", "DCS-03"),
    "DADM": ("DADM-01", "DADM-02"),
    "DPE": (),
    "DM": ("DM-01", "DM-02"),
}

DADM_MODALITIES: tuple[str, ...] = ("Presencial", "Semipresencial", "EAD")

KPI_META: dict[str, dict[str, Any]] = {
    "DTNH-01A": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS da Instituição · Alunos",
        "objective": "Medir a propensão de recomendação dos alunos em relação à UNIVC como instituição.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Relatório de Avaliação Institucional do SEI, pergunta oficial sobre recomendar a UNIVC.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O resultado institucional agrega as parcelas acadêmicas disponíveis de DTNH + DCS pelas contagens reais de respostas. A meta é institucional e não varia por curso.",
    },
    "DTNH-01B": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS do Curso",
        "objective": "Medir a propensão de recomendação dos alunos em relação ao próprio curso.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Relatório de Avaliação Institucional do SEI, pergunta oficial sobre recomendar o próprio curso.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O KPI é calculado por curso e pode usar meta geral da diretoria ou meta específica do curso. O NPS institucional é o KPI 01A.",
    },
    "DTNH-01C": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS da Instituição · Docentes",
        "objective": "Medir a propensão de recomendação da UNIVC pelos docentes.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Avaliação Institucional pelos docentes no SEI, pergunta oficial 0–10 sobre recomendar a UNIVC.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O relatório docente é institucional e anônimo. O resultado não é separado por curso, disciplina ou professor e a meta usa somente o recorte TOTAL.",
    },
    "DCS-01C": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS da Instituição · Docentes",
        "objective": "Medir a propensão de recomendação da UNIVC pelos docentes.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Avaliação Institucional pelos docentes no SEI, pergunta oficial 0–10 sobre recomendar a UNIVC.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O relatório docente é institucional e anônimo. O resultado não é separado por curso, disciplina ou professor e a meta usa somente o recorte TOTAL.",
    },
    # Código histórico mantido apenas para leitura de registros/arquivos antigos.
    "DTNH-01": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS do Curso · legado",
        "objective": "Código histórico substituído por DTNH-01B.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Histórico acadêmico anterior à divisão 01A/01B.",
        "periodicity": "Semestral",
        "help": "Código legado. Novas metas e planos devem usar DTNH-01A ou DTNH-01B.",
    },
    "DTNH-02": {
        "unit": "%", "direction": "higher", "short_name": "Favorabilidade docente",
        "objective": "Acompanhar a favorabilidade das avaliações realizadas pelos alunos sobre os docentes, preservando curso, disciplina, professor e semestre.",
        "formula": "Respostas favoráveis ÷ (favoráveis + intermediárias + desfavoráveis) × 100, somente nas perguntas sobre o docente.",
        "source": "Relatório Disciplina/Professor da Avaliação Institucional no SEI; categorias originais preservadas.",
        "periodicity": "Semestral",
        "help": "O KPI 02 é percentual de favorabilidade, não nota 0–10. 'Não sei' e equivalentes ficam fora do denominador; perguntas contextuais não compõem a síntese docente e categorias desconhecidas suspendem o percentual até revisão.",
    },
    "DTNH-03": {
        "unit": "%", "direction": "higher", "short_name": "Taxa de aprovação",
        "objective": "Medir aprovação e desempenho acadêmico, preservando nota final, situação oficial e motivo de reprovação.",
        "formula": "Alunos aprovados ÷ alunos com resultado final × 100.",
        "source": "Mapa de Nota do Aluno por Turma do SEI ou lançamento institucional equivalente.",
        "periodicity": "Semestral",
        "help": "A situação oficial do SEI define aprovação/reprovação. O sistema não recalcula a situação pela média.",
    },
    "DCS-01A": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS da Instituição · Alunos",
        "objective": "Medir a propensão de recomendação dos alunos em relação à UNIVC como instituição.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Relatório de Avaliação Institucional do SEI, pergunta oficial sobre recomendar a UNIVC.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O resultado institucional agrega as parcelas acadêmicas disponíveis de DTNH + DCS pelas contagens reais de respostas. A meta é institucional e não varia por curso.",
    },
    "DCS-01B": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS do Curso",
        "objective": "Medir a propensão de recomendação dos alunos em relação ao próprio curso.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Relatório de Avaliação Institucional do SEI, pergunta oficial sobre recomendar o próprio curso.",
        "periodicity": "Semestral / conforme aplicação",
        "help": "O KPI é calculado por curso e pode usar meta geral da diretoria ou meta específica do curso. O NPS institucional é o KPI 01A.",
    },
    # Código histórico mantido apenas para leitura de registros/arquivos antigos.
    "DCS-01": {
        "unit": "pontos", "direction": "higher", "short_name": "NPS do Curso · legado",
        "objective": "Código histórico substituído por DCS-01B.",
        "formula": "% Promotores (9–10) − % Detratores (0–6)",
        "source": "Histórico acadêmico anterior à divisão 01A/01B.",
        "periodicity": "Semestral",
        "help": "Código legado. Novas metas e planos devem usar DCS-01A ou DCS-01B.",
    },
    "DCS-02": {
        "unit": "%", "direction": "higher", "short_name": "Favorabilidade docente",
        "objective": "Acompanhar a favorabilidade das avaliações realizadas pelos alunos sobre os docentes, preservando curso, disciplina, professor e semestre.",
        "formula": "Respostas favoráveis ÷ (favoráveis + intermediárias + desfavoráveis) × 100, somente nas perguntas sobre o docente.",
        "source": "Relatório Disciplina/Professor da Avaliação Institucional no SEI; categorias originais preservadas.",
        "periodicity": "Semestral",
        "help": "O KPI 02 é percentual de favorabilidade, não nota 0–10. 'Não sei' e equivalentes ficam fora do denominador; perguntas contextuais não compõem a síntese docente e categorias desconhecidas suspendem o percentual até revisão.",
    },
    "DCS-03": {
        "unit": "%", "direction": "higher", "short_name": "Taxa de aprovação",
        "objective": "Medir aprovação e desempenho acadêmico, preservando nota final, situação oficial e motivo de reprovação.",
        "formula": "Alunos aprovados ÷ alunos com resultado final × 100.",
        "source": "Mapa de Nota do Aluno por Turma do SEI ou lançamento institucional equivalente.",
        "periodicity": "Semestral",
        "help": "A situação oficial do SEI define aprovação/reprovação. O sistema não recalcula a situação pela média.",
    },
    "DADM-01": {
        "unit": "%",
        "direction": "higher",
        "short_name": "Cumprimento do prazo",
        "objective": "Medir a agilidade e a resolutividade dos canais oficiais de atendimento.",
        "formula": "Solicitações atendidas no prazo ÷ solicitações recebidas × 100.",
        "source": "Registros dos canais oficiais: mensageria, e-mail institucional, protocolo presencial, ouvidoria e sistema de chamados.",
        "feeder": "Coordenação de Atendimento",
        "validator": "Diretor(a) Administrativo(a)",
        "target_text": "≥ 90% no prazo; atenção abaixo de 85%.",
        "target_value": 90.0,
        "periodicity": "Mensal",
        "cuts": "Canal, tipo de solicitação e semana",
        "help": "O canal é obrigatório em cada lançamento. O painel também acompanha reabertura, saldo em aberto e tempos médios de primeira resposta e resolução.",
    },
    "DADM-02": {
        "unit": "%",
        "direction": "higher",
        "short_name": "Satisfação",
        "objective": "Medir a satisfação das pessoas logo após o atendimento, com instrumento comum aos canais.",
        "formula": "Respostas 4 e 5 ÷ respondentes × 100.",
        "source": "Pesquisa pós-atendimento com instrumento e escala idênticos em todos os canais.",
        "feeder": "Coordenação de Atendimento",
        "validator": "Diretor(a) Administrativo(a)",
        "target_text": "≥ 80% consolidado; abaixo de 25% de resposta, a amostra é indicativa.",
        "target_value": 80.0,
        "periodicity": "Mensal",
        "cuts": "Canal, tipo de solicitação e faixa de resolução",
        "help": "O painel apresenta satisfação, insatisfação e taxa de resposta. A leitura deve sempre considerar a representatividade da amostra.",
    },


}

DADM_HEADER_ALIASES = {
    "dadm-evasao": {
        "periodo": {"periodo", "mes", "competencia"},
        "diretoria_academica": {"diretoria academica", "diretoria", "area academica"},
        "curso": {"curso"},
        "desligamentos": {"desligamentos", "desligamentos no mes", "evasoes"},
    },
    "dadm-custos": {
        "periodo": {"periodo", "mes", "competencia"},
        "centro_custo": {"centro de custo", "centro custo", "centro de custo administrativo"},
        "modalidade": {"modalidade"},
        "despesa": {"despesa", "despesa administrativa", "valor", "custo"},
    },
    "dadm-infraestrutura": {
        "periodo": {"periodo", "mes", "competencia"},
        "despesa": {"despesa", "despesa de infraestrutura", "despesa de infraestrutura e manutencao", "custo"},
        "area_m2": {"area em uso m2", "area em uso", "m2 em uso", "area m2"},
    },
}
