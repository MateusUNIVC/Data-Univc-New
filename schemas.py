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
ACADEMIC_UI_DATASETS: tuple[str, ...] = ("avaliacao_docente", "resultados")

IMPLEMENTED_KPIS: dict[str, tuple[str, ...]] = {
    "DTNH": ("DTNH-01A", "DTNH-01B", "DTNH-01C", "DTNH-02", "DTNH-03"),
    "DCS": ("DCS-01A", "DCS-01B", "DCS-01C", "DCS-02", "DCS-03"),
    "DADM": ("DADM-01", "DADM-02"),
    "DPE": ("DPE-01", "DPE-02", "DPE-03"),
    "DM": ("DM-01", "DM-02"),
}

DADM_MODALITIES: tuple[str, ...] = ("Presencial", "Semipresencial", "EAD")
DPE_RESULT_SCOPE_TYPES: tuple[str, ...] = ("Institucional", "Modalidade", "Polo", "Curso", "Programa stricto sensu")
DPE_CASH_MOVEMENT_TYPES: tuple[str, ...] = ("Entrada", "Saída")

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
        "unit": "nota", "direction": "higher", "short_name": "Avaliação docente",
        "objective": "Acompanhar a avaliação dos docentes realizada pelos alunos, por curso, disciplina e professor.",
        "formula": "Média ponderada das notas de avaliação pelo número de respondentes.",
        "source": "Instrumento institucional de avaliação docente pelo aluno; integração SEI preparada para o primeiro relatório real.",
        "periodicity": "Semestral",
        "help": "A arquitetura preserva professor, disciplina, curso, turma/oferta e semestre. A leitura pode ser numérica ou categórica conforme o questionário real.",
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
        "unit": "nota", "direction": "higher", "short_name": "Avaliação docente",
        "objective": "Acompanhar a avaliação dos docentes realizada pelos alunos, por curso, disciplina e professor.",
        "formula": "Média ponderada das notas de avaliação pelo número de respondentes.",
        "source": "Instrumento institucional de avaliação docente pelo aluno; integração SEI preparada para o primeiro relatório real.",
        "periodicity": "Semestral",
        "help": "A arquitetura preserva professor, disciplina, curso, turma/oferta e semestre. A leitura pode ser numérica ou categórica conforme o questionário real.",
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
    "DPE-01": {
        "unit": "%",
        "secondary_unit": "R$",
        "direction": "higher",
        "short_name": "Resultado operacional",
        "objective": "Consolidar receita e despesa em um único indicador de sustentabilidade, no total e nos recortes gerenciais previstos.",
        "formula": "((Receita líquida − Despesa total) ÷ Receita líquida) × 100",
        "source": "Setor Financeiro — DRE gerencial mensal com centros de custo por modalidade, polo, curso e programa.",
        "feeder": "Setor Financeiro",
        "validator": "Diretor(a) da DPE",
        "target_text": "≥ 10% institucional; ≥ 20% de margem de contribuição por polo",
        "target_value": 10.0,
        "periodicity": "Mensal",
        "cycle": "Ciclo 1 — set/2026",
        "cuts": "Obrigatórios: institucional; modalidade; polo; programa stricto sensu. Curso é dimensão operacional adicional disponível na DRE.",
        "origin": "REI05 + DEMD03 + DEMD04 + DEMD07 + DM06",
        "help": "Informe receita líquida e despesa total para um recorte. O sistema calcula automaticamente resultado em R$ e margem em %. Para Institucional, o recorte é TOTAL.",
    },
    "DPE-04": {
        "unit": "%",
        "secondary_unit": "R$",
        "direction": "range",
        "short_name": "Execução orçamentária",
        "objective": "Comparar o realizado com o orçado por centro de custo, dando previsibilidade à Reitoria.",
        "formula": "(Despesa realizada no mês ÷ Despesa orçada no mês) × 100",
        "source": "Orçamento anual aprovado + razão contábil.",
        "feeder": "Setor Financeiro / Contabilidade",
        "validator": "Diretor(a) da DPE",
        "target_text": "Entre 95% e 105%",
        "target_value": 95.0,
        "attention_value": 90.0,
        "upper_limit": 105.0,
        "periodicity": "Mensal",
        "cycle": "Ciclo 2 — out/2026",
        "cuts": "Diretoria e centro de custo",
        "origin": "DA02",
        "help": "Meta em faixa: use 95 como limite inferior e 105 como limite superior. Acima de 105% também é desvio, pois indica estouro orçamentário.",
    },
    "DPE-05": {
        "unit": "R$",
        "direction": "higher",
        "short_name": "Saldo operacional de caixa",
        "objective": "Acompanhar a liquidez mensal e antecipar necessidade de ajuste de desembolsos.",
        "formula": "Entradas do mês − Saídas do mês (e saldo acumulado)",
        "source": "Extratos e fluxo de caixa consolidado.",
        "feeder": "Setor Financeiro",
        "validator": "Diretor(a) da DPE",
        "target_text": "Saldo mensal positivo e reserva equivalente a, no mínimo, uma folha de pagamento",
        "target_value": 0.0,
        "periodicity": "Mensal",
        "cycle": "Ciclo 2 — out/2026",
        "cuts": "Conta e natureza de desembolso",
        "origin": "DA03",
        "help": "Cadastre movimentos mensais agregados por conta, tipo (Entrada/Saída) e natureza. O sistema calcula entradas, saídas, saldo do mês e saldo acumulado do histórico carregado. A condição de reserva mínima de uma folha fica sinalizada como pendente até a folha/DPE-06 ser integrada.",
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

DPE_HEADER_ALIASES = {
    "dpe-resultado": {
        "periodo": {"periodo", "mes", "competencia"},
        "tipo_recorte": {"tipo de recorte", "tipo recorte", "dimensao", "nivel"},
        "recorte": {"recorte", "valor do recorte", "descricao"},
        "receita_liquida": {"receita liquida", "receita liquida r", "receita"},
        "despesa_total": {"despesa total", "despesa total r", "despesa"},
    },
    "dpe-orcamento": {
        "periodo": {"periodo", "mes", "competencia"},
        "unidade": {"diretoria", "unidade", "unidade gestora", "unidade orcamentaria"},
        "centro_custo": {"centro de custo", "centro custo"},
        "despesa_orcada": {"despesa orcada", "orcado", "orcamento", "despesa orcada r"},
        "despesa_realizada": {"despesa realizada", "realizado", "despesa realizada r"},
    },
    "dpe-caixa": {
        "periodo": {"periodo", "mes", "competencia"},
        "conta": {"conta", "conta bancaria", "caixa"},
        "tipo_movimento": {"tipo de movimento", "tipo movimento", "movimento"},
        "natureza": {"natureza", "natureza do movimento", "natureza do desembolso"},
        "valor": {"valor", "valor r", "montante"},
    },
}
