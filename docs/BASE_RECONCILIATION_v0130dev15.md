# Reconciliação de base — v0.13.0-dev.15

## Objetivo

Reconciliar a DPE consolidada v0.13.0-dev.14, originalmente construída sobre a árvore acadêmica v0.11.6.5, com a árvore acadêmica completa v0.11.6.7.

## Método

Foi utilizado merge de três vias:

- ancestral comum: `UNIVC_Data_Driven_Cloud_v0.11.6.5_ACADEMIC_RESULTS_STUDENT_UX`;
- ramo acadêmico: `UNIVC_Data_Driven_Cloud_v0.11.6.7_ACADEMIC_RESULTS_STUDENT_CLASSIFICATION`;
- ramo DPE: `Data_UNIVC_v0.13.0-dev.14_DPE14_FINAL_AUDIT_BASE_v0.11.6.5`.

A diferença acadêmica 11.6.5 → 11.6.7 contém 17 arquivos. Apenas seis também tinham alterações no ramo DPE; cinco eram metadados/documentação e o único arquivo de código compartilhado era `repository.py`. O merge de `repository.py` foi limpo, sem conflitos.

## Mudanças acadêmicas integradas

- `academic_excel_parser.py`;
- `repository.py` com a classificação gerencial v0.11.6.7 por aluno;
- `static/js/app.js`;
- `static/css/app.css`;
- `templates/index.html`;
- verificadores v0.11.6.6 e v0.11.6.7;
- testes acadêmicos v0.11.6.5, v0.11.6.6 e v0.11.6.7;
- documentação acadêmica correspondente.

## Preservação da DPE

Foram mantidos integralmente:

- schema 48 e migrations DPE 041–048;
- Cost Engine;
- ledger moderno de receitas;
- tratamentos de despesas;
- domínio de docência;
- distribuição/rateio;
- resultado consolidado;
- metas e planos;
- UX final;
- Excel moderno;
- bloqueio do legado DPE-01/02/03;
- `scripts/run_release_checks.py`.

## Regra de release

A v0.13.0-dev.15 é a primeira árvore completa DPE 0.13 baseada oficialmente na v0.11.6.7 acadêmica.
