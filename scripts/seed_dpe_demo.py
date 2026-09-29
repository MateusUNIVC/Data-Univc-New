from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser(description="Inicializa a demonstracao local da DPE.")
parser.add_argument("--reset", action="store_true", help="Apaga o SQLite local antes de recriar a demonstracao.")
args = parser.parse_args()

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("DEFAULT_DIRECTORATE_CODE", "DPE")
os.environ.setdefault("AUTO_CREATE_DB", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("REQUIRE_SCHEMA_VERSION", "false")
os.environ.setdefault("DPE_LOCAL_DEMO", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./univc_dpe_demo.db")

db_url = os.environ["DATABASE_URL"]
if not db_url.startswith("sqlite"):
    raise SystemExit("A carga demonstrativa e bloqueada para bancos que nao sejam SQLite local.")
if args.reset:
    prefix = "sqlite:///"
    if db_url.startswith(prefix):
        db_path = (ROOT / db_url[len(prefix):]).resolve()
        if db_path.exists():
            db_path.unlink()

from sqlalchemy import select
from database import Base, SessionLocal, engine
from schema_version import ensure_local_schema_version
from models import Course, Directorate, DPEAllocationRule, DPECostPeriod
from security import DirectorateGrant, DirectorateScope, UserContext
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_expenses import DPECostExpenseRepository
from dpe_cost_teaching import DPECostTeachingRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from dpe_cost_allocation import DPECostAllocationRepository
from management_repository import ManagementRepository

DIRECTORATES = {
    "DTNH": "Diretoria de Tecnologia, Negócios e Humanidades",
    "DCS": "Diretoria de Ciências da Saúde",
    "DADM": "Diretoria Administrativa",
    "DPE": "Diretoria de Planejamento Econômico e Oferta",
    "DM": "Diretoria de Mestrado",
}
RULES = [
    ("DIRECT", "Direto para curso/contexto", "DIRECT", "Despesa diretamente atribuida a um curso/contexto."),
    ("TEACHER_HOURS", "Carga horaria docente", "TEACHER_HOURS", "Custo docente distribuido pela carga horaria registrada do docente."),
    ("OFFERING_HOURS", "Carga horaria do contexto", "OFFERING_HOURS", "Custos compartilhados pela carga horaria dos cursos/contextos."),
    ("STUDENTS", "Quantidade de alunos", "STUDENTS", "Custos compartilhados pela quantidade de alunos ativos."),
    ("REVENUE", "Receita de curso", "REVENUE", "Custos compartilhados proporcionalmente a Receita de curso."),
    ("EQUAL", "Divisao igualitaria", "EQUAL", "Divisao igual entre os cursos/contextos elegiveis."),
    ("MANUAL", "Rateio manual", "MANUAL", "Percentuais ou valores definidos manualmente."),
]

PRODUCTS = [
    ("ADM", "Administração"), ("DIR", "Direito"), ("ADS", "Análise e Desenvolvimento de Sistemas"),
    ("CCONT", "Ciências Contábeis"), ("ENGMEC", "Engenharia Mecânica"), ("ENGPROD", "Engenharia de Produção"),
    ("ARQ", "Arquitetura e Urbanismo"), ("COMSOC", "Comunicação Social"), ("AGRO", "Agronomia"),
    ("ODONTO", "Odontologia"), ("FISIO", "Fisioterapia"), ("ENF", "Enfermagem"),
    ("PSI", "Psicologia"), ("EDF", "Educação Física"), ("FARM", "Farmácia"), ("MEDVET", "Medicina Veterinária"),
]

OFFERINGS = [
    ("ADM-NOT", "ADM", "PRESENCIAL", "Noturno"),
    ("DIR-MAT", "DIR", "PRESENCIAL", "Matutino"), ("DIR-NOT", "DIR", "PRESENCIAL", "Noturno"),
    ("ADS-NOT", "ADS", "PRESENCIAL", "Noturno"),
    ("CCONT-NOT", "CCONT", "PRESENCIAL", "Noturno"),
    ("ENGMEC-NOT", "ENGMEC", "PRESENCIAL", "Noturno"), ("ENGPROD-NOT", "ENGPROD", "PRESENCIAL", "Noturno"),
    ("ARQ-NOT", "ARQ", "PRESENCIAL", "Noturno"), ("COMSOC-NOT", "COMSOC", "PRESENCIAL", "Noturno"),
    ("AGRO-INT", "AGRO", "PRESENCIAL", "Integral"), ("ODONTO-INT", "ODONTO", "PRESENCIAL", "Integral"),
    ("FISIO-MAT", "FISIO", "PRESENCIAL", "Matutino"),
    ("ENF-MAT", "ENF", "PRESENCIAL", "Matutino"), ("ENF-NOT", "ENF", "PRESENCIAL", "Noturno"),
    ("PSI-MAT", "PSI", "PRESENCIAL", "Matutino"), ("PSI-NOT", "PSI", "PRESENCIAL", "Noturno"),
    ("EDF-NOT", "EDF", "PRESENCIAL", "Noturno"), ("FARM-NOT", "FARM", "PRESENCIAL", "Noturno"),
    ("MEDVET-INT", "MEDVET", "PRESENCIAL", "Integral"),
]

TEACHERS = [
    "Ana Paula Ribeiro", "Bruno Fernandes Costa", "Carla Mendes Rocha", "Daniel Oliveira Santos",
    "Eduarda Lima Martins", "Felipe Almeida Souza", "Gabriela Nunes Vieira", "Henrique Barros Silva",
    "Isabela Carvalho Reis", "Joao Pedro Azevedo", "Karen Cristina Moraes", "Lucas Matos Ferreira",
    "Mariana Lopes Ribeiro", "Nicolas Gomes Freitas", "Olivia Cardoso Lima", "Paulo Henrique Dias",
    "Renata Alves Campos", "Samuel Rocha Pinto", "Tatiana Martins Costa", "Victor Hugo Almeida",
    "Wesley Nunes Andrade", "Yasmin Barros Souza", "Caio Vinicius Reis", "Larissa Gomes Farias",
]

Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    ensure_local_schema_version(conn)

with SessionLocal() as db:
    for code, name in DIRECTORATES.items():
        row = db.scalar(select(Directorate).where(Directorate.code == code))
        if not row:
            db.add(Directorate(code=code, name=name, active=True))
    db.commit()
    dpe = db.scalar(select(Directorate).where(Directorate.code == "DPE"))
    dtnh = db.scalar(select(Directorate).where(Directorate.code == "DTNH"))
    dcs = db.scalar(select(Directorate).where(Directorate.code == "DCS"))
    assert dpe and dtnh and dcs

    # v0.13: o DPE operacional nasce do catalogo academico oficial; modalidade nao limita a participacao.
    dcs_codes = {"ODONTO", "FISIO", "ENF", "PSI", "EDF", "FARM", "MEDVET"}
    official_courses = {}
    for code, name in PRODUCTS:
        owner = dcs if code in dcs_codes else dtnh
        row = db.scalar(select(Course).where(Course.directorate_id == owner.id, Course.name == name))
        if not row:
            row = Course(
                directorate_id=owner.id, name=name, modality="Presencial", active=True,
                valid_from="2026-01", valid_to=None,
            )
            db.add(row)
            db.flush()
        official_courses[code] = row
    db.commit()
    for code, name, driver, description in RULES:
        if not db.scalar(select(DPEAllocationRule).where(DPEAllocationRule.directorate_id == dpe.id, DPEAllocationRule.code == code)):
            db.add(DPEAllocationRule(
                directorate_id=dpe.id, code=code, name=name, driver_type=driver,
                description=description, parameters_json={}, system_defined=True, active=True,
                created_by="demo.local@univc.invalid",
            ))
    db.commit()

    user = UserContext(
        user_id="dpe-demo-local", email="demo.dpe@univc.local", full_name="Demonstracao DPE",
        role="admin", directorate_id=dpe.id, directorate_code="DPE", directorate_name=dpe.name,
        global_role="DIRECTORATE", permission_version=1,
        directorate_access=(DirectorateGrant(dpe.id, "DPE", dpe.name, "EDIT", True),), session_id="dpe-demo-session",
    )
    scope = DirectorateScope(user=user, directorate_id=dpe.id, directorate_code="DPE", directorate_name=dpe.name, can_write=True, is_home=True)

    if db.scalar(select(DPECostPeriod.id).where(DPECostPeriod.directorate_id == dpe.id, DPECostPeriod.period == "2026-09")):
        print("Demonstracao DPE ja existe. Use --reset para recriar do zero.")
        raise SystemExit(0)

    catalog = DPECostCatalogRepository(db, scope)
    expenses = DPECostExpenseRepository(db, scope)
    teaching = DPECostTeachingRepository(db, scope)
    economics = DPECostEconomicsRepository(db, scope)
    revenues = DPERevenueRepository(db, scope)
    allocation = DPECostAllocationRepository(db, scope)

    products = {}
    for code, name in PRODUCTS:
        products[code] = catalog.create_product({
            "code": code,
            "source_course_id": official_courses[code].id,
            "notes": "Dado ficticio para homologacao local.",
        })

    offering_master = {}
    for code, product_code, modality, shift in OFFERINGS:
        offering_master[code] = catalog.create_offering({
            "product_id": products[product_code]["id"], "code": code, "modality": modality, "shift": shift,
            "campus": "São Mateus", "unit_name": "Campus Sede", "pole_name": None,
            "valid_from": "2026-01", "notes": "Contexto ficticio para demonstracao local.",
        })

    period = catalog.create_period({"period": "2026-09", "notes": "Competencia ficticia para testes da DPE V2.", "materialize_offerings": True})
    catalog.update_period(period["id"], {"status": "REVIEW"})
    period = catalog.get_period(period["id"])
    snapshot_by_code = {item["offering"]["code"]: item for item in period["offerings"] if item["included"]}

    rules = {r.code: r for r in db.scalars(select(DPEAllocationRule).where(DPEAllocationRule.directorate_id == dpe.id)).all()}

    centers = {}
    for code, name in [
        ("ACADEMICO", "Acadêmico"), ("ADMIN", "Administrativo"), ("INFRA", "Infraestrutura e manutenção"),
        ("TI", "Tecnologia da informação"), ("MKT", "Marketing e comunicação"), ("LAB", "Laboratórios e clínicas"),
        ("BIB", "Biblioteca"), ("RH", "Recursos humanos"),
    ]:
        centers[code] = expenses.create_cost_center({"code": code, "name": name, "notes": "Centro ficticio para homologacao."})

    categories = {}
    category_specs = [
        ("DOCENTE", "Custo docente", "TEACHER_HOURS"),
        ("MANUT", "Manutenção predial", "OFFERING_HOURS"),
        ("ENERGIA", "Energia e utilidades", "OFFERING_HOURS"),
        ("SERVICOS", "Serviços compartilhados", "STUDENTS"),
        ("TECNOLOGIA", "Tecnologia e sistemas", "STUDENTS"),
        ("MARKETING", "Marketing institucional", "REVENUE"),
        ("ADMINISTRATIVO", "Administrativo geral", "REVENUE"),
        ("BIBLIOTECA", "Biblioteca e acervo", "STUDENTS"),
        ("ESPECIFICO", "Custo direto de curso", "DIRECT"),
        ("COMPARTILHADO", "Despesa compartilhada igualitária", "EQUAL"),
    ]
    for code, name, rule_code in category_specs:
        categories[code] = expenses.create_category({"code": code, "name": name, "default_rule_id": rules[rule_code].id, "notes": "Categoria ficticia para homologacao."})

    teacher_rows = []
    relationship_cycle = ("EMPLOYEE", "HOURLY", "SERVICE_PROVIDER", "EMPLOYEE")
    for idx, name in enumerate(TEACHERS, 1):
        row = teaching.create_teacher({
            "display_name": name,
            "external_id": f"DEMO-PROF-{idx:03d}",
            "relationship_type": relationship_cycle[(idx - 1) % len(relationship_cycle)],
            "profile_notes": "Perfil docente ficticio para homologacao local.",
        })
        teacher_rows.append(row)
        teaching.create_alias(row["id"], {"alias_name": f"{name.upper()} DEMO", "source_type": "PAYROLL"})

    subject_rows = {}
    for idx, (product_code, product_name) in enumerate(PRODUCTS, 1):
        subject_rows[product_code] = [
            teaching.create_subject({"code": f"{product_code}-A", "name": f"Fundamentos Aplicados de {product_name}"}),
            teaching.create_subject({"code": f"{product_code}-B", "name": f"Projeto Integrador de {product_name}"}),
        ]

    # Duas atividades por oferta; os professores se repetem entre ofertas para exercitar rateio multi-curso.
    teacher_has_activity = set()
    for idx, (off_code, product_code, modality, shift) in enumerate(OFFERINGS):
        snap = snapshot_by_code[off_code]
        for slot in range(2):
            teacher = teacher_rows[(idx * 2 + slot * 7) % len(teacher_rows)]
            subject = subject_rows[product_code][slot]
            hours = Decimal("60") if slot == 0 else Decimal("40")
            teaching.create_activity({
                "period_id": period["id"], "teacher_id": teacher["id"], "subject_id": subject["id"],
                "class_group": f"{off_code}-T1", "workload_hours": str(hours),
                "effective_start_date": "2026-09-01", "effective_end_date": "2026-09-30",
                "workload_reference": "Carga ficticia setembro/2026", "source_type": "MANUAL",
                "offering_allocations": [{"period_offering_id": snap["id"], "allocated_hours": str(hours)}],
                "notes": "Atividade ficticia para homologacao local.",
            })
            teacher_has_activity.add(teacher["id"])

    # Exemplo explicito de aula compartilhada entre Direito Matutino e Noturno.
    shared_teacher = teacher_rows[0]
    shared_subject = teaching.create_subject({"code": "DIR-COMP", "name": "Topicos Juridicos Compartilhados"})
    teaching.create_activity({
        "period_id": period["id"], "teacher_id": shared_teacher["id"], "subject_id": shared_subject["id"],
        "class_group": "DIR-COMP-2026", "workload_hours": "90",
        "effective_start_date": "2026-09-08", "effective_end_date": "2026-09-29", "source_type": "MANUAL",
        "offering_allocations": [
            {"period_offering_id": snapshot_by_code["DIR-MAT"]["id"], "allocated_hours": "45"},
            {"period_offering_id": snapshot_by_code["DIR-NOT"]["id"], "allocated_hours": "45"},
        ],
        "notes": "Exemplo ficticio de disciplina compartilhada entre dois turnos.",
    })
    teacher_has_activity.add(shared_teacher["id"])

    # Alunos ativos e Receita de curso sao fatos separados no DPE-06.
    course_revenues = []
    for idx, (off_code, *_rest) in enumerate(OFFERINGS):
        snap_id = snapshot_by_code[off_code]["id"]
        active = 58 + ((idx * 17) % 123)
        economics.upsert(period["id"], snap_id, {
            "active_students": active,
            "source_type": "MANUAL",
            "source_reference": "DEMO-2026-09",
            "notes": "Alunos ativos ficticios para teste local.",
        })
        # Valor direto de receita; nao ha bruto, bolsas, deducoes ou pagantes.
        revenue = (Decimal(active) * Decimal(980 + idx * 32)).quantize(Decimal("0.01"))
        course_revenues.append({"period_offering_id": snap_id, "amount": str(revenue)})
    revenues.bulk_courses(period["id"], course_revenues)

    revenue_categories = {row["code"]: row for row in revenues.central(period["id"])["categories"]}
    revenues.create(period["id"], {
        "category_id": revenue_categories["ROOM_RENTAL"]["id"],
        "description": "Aluguel de sala para atividade externa",
        "amount": "8500.00",
        "source_type": "MANUAL",
        "notes": "Receita institucional ficticia sem atribuicao a curso.",
    })
    revenues.create(period["id"], {
        "category_id": revenue_categories["SPORTS_RENTAL"]["id"],
        "description": "Aluguel de quadra para evento externo",
        "amount": "4200.00",
        "source_type": "MANUAL",
        "notes": "Receita institucional ficticia sem atribuicao a curso.",
    })
    revenues.create(period["id"], {
        "category_id": revenue_categories["EVENTS"]["id"],
        "period_offering_id": snapshot_by_code["ADM-NOT"]["id"],
        "description": "Evento executivo vinculado a Administracao",
        "amount": "3100.00",
        "source_type": "MANUAL",
        "notes": "Exemplo ficticio de outra receita explicitamente atribuida a um curso/contexto.",
    })

    # Custos docentes: somente docentes que efetivamente possuem atividade na competencia.
    payroll_expenses = []
    for idx, teacher in enumerate(teacher_rows):
        if teacher["id"] not in teacher_has_activity:
            continue
        amount = Decimal(4800 + (idx % 8) * 620 + (idx % 3) * 175).quantize(Decimal("0.01"))
        exp = expenses.create_expense({
            "period_id": period["id"], "expense_date": "2026-09-05", "description": f"Custo docente - {teacher['display_name']}",
            "amount": str(amount), "expense_kind": "PAYROLL", "counterparty_name": teacher["display_name"],
            "document_number": f"FOLHA-DEMO-{idx+1:03d}", "cost_center_id": centers["ACADEMICO"]["id"],
            "category_id": categories["DOCENTE"]["id"], "source_type": "MANUAL", "source_reference": "FOLHA-DEMO-2026-09",
            "notes": "Valor ficticio para homologacao local.",
        })
        teaching.link_payroll_expense(exp["id"], {"teacher_id": teacher["id"], "match_method": "MANUAL"})
        payroll_expenses.append(exp)

    general_specs = [
        ("Manutencao preventiva dos predios", "42000", "INFRA", "MANUT", None),
        ("Energia eletrica do campus", "38500", "INFRA", "ENERGIA", None),
        ("Limpeza e conservacao", "31800", "INFRA", "SERVICOS", None),
        ("Seguranca patrimonial", "24600", "INFRA", "COMPARTILHADO", None),
        ("Licencas ERP e sistemas academicos", "18900", "TI", "TECNOLOGIA", None),
        ("Internet, links e data center", "15400", "TI", "TECNOLOGIA", None),
        ("Biblioteca digital e periodicos", "12600", "BIB", "BIBLIOTECA", None),
        ("Campanhas institucionais de captacao", "27600", "MKT", "MARKETING", None),
        ("Servicos administrativos compartilhados", "22400", "ADMIN", "ADMINISTRATIVO", None),
        ("Materiais clinicos de Odontologia", "16800", "LAB", "ESPECIFICO", "ODONTO-INT"),
        ("Insumos da clinica veterinaria", "14750", "LAB", "ESPECIFICO", "MEDVET-INT"),
        ("Materiais do laboratorio de Engenharia Mecanica", "11300", "LAB", "ESPECIFICO", "ENGMEC-NOT"),
        ("Materiais do laboratorio de Engenharia de Producao", "8450", "LAB", "ESPECIFICO", "ENGPROD-NOT"),
        ("Plotagem e materiais de Arquitetura", "5300", "LAB", "ESPECIFICO", "ARQ-NOT"),
        ("Manutencao de equipamentos de saude", "20200", "LAB", "COMPARTILHADO", ["FISIO-MAT", "ENF-MAT", "ENF-NOT", "FARM-NOT"]),
        ("Servico de apoio pedagogico", "13100", "ACADEMICO", "SERVICOS", None),
    ]
    demo_expenses = {}
    institutional_demo = {"Campanhas institucionais de captacao"}
    for idx, (description, amount, center_code, category_code, target) in enumerate(general_specs, 1):
        expense_scope = "DIRECT" if isinstance(target, str) else ("INSTITUTIONAL" if description in institutional_demo else "SHARED")
        payload = {
            "period_id": period["id"], "expense_date": f"2026-09-{10 + (idx % 15):02d}", "description": description,
            "amount": amount, "expense_kind": "GENERAL", "expense_scope": expense_scope,
            "counterparty_name": "Fornecedor Ficticio UNIVC",
            "document_number": f"NF-DEMO-{idx:04d}", "cost_center_id": centers[center_code]["id"],
            "category_id": categories[category_code]["id"], "source_type": "MANUAL", "source_reference": "DEMO-DESPESAS-2026-09",
            "notes": "Despesa ficticia para homologacao local.",
        }
        if isinstance(target, str):
            payload["direct_period_offering_id"] = snapshot_by_code[target]["id"]
        exp = expenses.create_expense(payload)
        if isinstance(target, list):
            allocation.set_expense_config(exp["id"], {"targets": [{"period_offering_id": snapshot_by_code[code]["id"]} for code in target]})
        demo_expenses[description] = exp

    # Politicas reutilizaveis ficticias para homologar a v0.12.1.
    allocation.create_policy_from_expense(demo_expenses["Energia eletrica do campus"]["id"], {
        "name": "Energia - politica padrao", "auto_suggest": True,
        "notes": "Exemplo ficticio: reaplica o mesmo criterio quando a despesa recorrente voltar no mes seguinte.",
    })
    allocation.create_policy_from_expense(demo_expenses["Manutencao de equipamentos de saude"]["id"], {
        "name": "Manutencao saude - cursos atendidos", "auto_suggest": True,
        "notes": "Exemplo ficticio com escopo restrito a ofertas da area da saude.",
    })

    # Um lote de entrada em staging para testar a separacao entre importacao e despesa oficial.
    batch = expenses.create_import_batch({
        "period_id": period["id"], "source_type": "EXCEL", "source_label": "Despesas ficticias pendentes",
        "original_filename": "despesas_demo_pendentes.xlsx", "external_key": "DEMO-STAGING",
        "notes": "Lote ficticio ainda nao incorporado ao ledger oficial.",
    })
    expenses.stage_rows(batch["id"], [
        {"raw_data": {"descricao": "Material de escritorio", "valor": "780,00"}, "normalized_data": {"description": "Material de escritorio", "amount": 780.0}},
        {"raw_data": {"descricao": "Pequeno reparo predial", "valor": "1250,00"}, "normalized_data": {"description": "Pequeno reparo predial", "amount": 1250.0}},
        {"raw_data": {"descricao": "Assinatura de software", "valor": "490,00"}, "normalized_data": {"description": "Assinatura de software", "amount": 490.0}},
    ])

    # Metas e plano demonstrativos usam exclusivamente as métricas canônicas da DPE.
    management = ManagementRepository(db, scope)
    management.save_target({
        "indicator_code": "DPE-RESULT", "metric_key": "institutional_margin_pct",
        "valid_from": "2026-09", "target": 85, "attention": 80,
        "dimensions": {}, "justification": "Meta fictícia para homologar a leitura automática do resultado institucional.",
    })
    management.save_target({
        "indicator_code": "DPE-REVENUE", "metric_key": "total_revenue",
        "valid_from": "2026-09", "target": 2700000, "attention": 2600000,
        "dimensions": {}, "justification": "Meta fictícia de receita total.",
    })
    management.save_target({
        "indicator_code": "DPE-EXPENSE", "metric_key": "total_expense",
        "valid_from": "2026-09", "target": 480000, "attention": 520000,
        "dimensions": {}, "justification": "Meta fictícia de controle das despesas totais.",
    })
    management.save_target({
        "indicator_code": "DPE-EXPENSE", "metric_key": "institutional_expense",
        "valid_from": "2026-09", "target": 20000, "attention": 25000,
        "dimensions": {}, "justification": "Exemplo de meta deliberadamente fora do alvo para homologar o fluxo de plano de ação.",
    })
    management.save_target({
        "indicator_code": "DPE-ALLOCATION", "metric_key": "reconciliation_pct",
        "valid_from": "2026-09", "target": 100, "attention": 99.5,
        "dimensions": {}, "justification": "Toda despesa distribuível deve ser conciliada.",
    })
    management.save_target({
        "indicator_code": "DPE-RESULT", "metric_key": "course_margin_pct",
        "valid_from": "2026-09", "target": 80, "attention": 70,
        "dimensions": {"course": "Administração", "academic_directorate": "DTNH"},
        "justification": "Meta fictícia específica do curso para homologar escopo dimensional.",
    })
    management.save_action({
        "indicator_code": "DPE-EXPENSE", "metric_key": "institutional_expense",
        "period": "2026-09", "dimensions": {},
        "problem": "Despesa institucional acima do patamar definido para a competência.",
        "probable_cause": "Campanha institucional extraordinária concentrada no mês.",
        "corrective_action": "Revisar despesas institucionais recorrentes e separar ações extraordinárias do orçamento mensal.",
        "responsible": "Coordenação DPE", "due_date": "2026-10-20",
        "status": "Em andamento", "evidence": "Plano fictício para homologação local.",
    })

    run = allocation.calculate(period["id"])
    if run["status"] != "CALCULATED" or abs(run["unallocated_total"]) > 0.001:
        print("ATENCAO: demonstracao criada, mas o rateio ficou com pendencias:")
        print(run)
    else:
        run = allocation.make_official(run["id"])
        print(f"Demonstracao pronta: competencia 2026-09, rateio v{run['run_number']} oficial e reconciliado, pronta para o checklist de fechamento.")
    print(f"Cursos: {len(PRODUCTS)} | Contextos: {len(OFFERINGS)} | Receitas de curso: {len(course_revenues)} | Outras receitas: 3 | Docentes com atividade: {len(teacher_has_activity)} | Custos docentes: {len(payroll_expenses)} | Despesas gerais: {len(general_specs)}")
