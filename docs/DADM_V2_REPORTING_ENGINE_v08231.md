# DADM V2 Reporting Engine — v0.8.23.1

## Objetivo

Criar a infraestrutura de relatórios da Diretoria Administrativa antes de qualquer alteração visual da próxima etapa. O relatório deve representar exatamente o contexto analítico TALLOS V2 e permanecer leve mesmo quando a base contém milhares de atendimentos.

## Rota

`GET /api/dadm/v2/report.xlsx`

Parâmetros opcionais, iguais aos filtros do DADM V2:

- `from_month` / `to_month` (`AAAA-MM`);
- `department`;
- `employee`;
- `channel`;
- `status`;
- `tabulation`.

A rota é de leitura e usa `current_scope`; usuários com acesso somente leitura à DADM também podem gerar o relatório do contexto que podem consultar.

## Contrato de privacidade e escala

O Excel não recebe uma linha por atendimento. As consultas agregam no banco por período, departamento e operador. Não são exportados `source_id`, `customer_ref`, nome/telefone/documento do cliente ou payload TALLOS.

Os relatórios não herdam limites de apresentação do dashboard, como top 100 operadores. Todos os operadores/departamentos encontrados no recorte são incluídos como agregados. O limite analítico de período do DADM V2 continua sendo 60 meses.

## Workbook

1. **Resumo** — totais, TME/TMA médio/mediana/P90, avaliação, cobertura e situação operacional, além de gráficos nativos.
2. **Evolução mensal** — uma linha por mês existente no recorte.
3. **Departamentos** — totais agregados de todos os departamentos do recorte.
4. **Operadores** — totais agregados de todos os operadores do recorte.
5. **Departamento x mês** — granularidade mensal para exploração com filtros do Excel.
6. **Operador x mês** — granularidade mensal para exploração com filtros do Excel.
7. **Avaliações** — distribuição homologada de 1 a 10.
8. **Parâmetros** — filtros aplicados, versão, sincronização e contrato de auditoria.

Tabelas usam o recurso nativo `Table` do XLSX, portanto possuem autofiltros. Gráficos são objetos nativos do Excel e permanecem editáveis.

## Semântica

- TME e TMA são exportados como duração Excel, não como texto.
- Nota válida continua sendo 1–10.
- `NULL`, `S/A` e o `level=0` normalizado continuam ausentes e não participam da média.
- Não existe conversão automática de nota em percentual de satisfação.
- Cobertura das avaliações e taxa de finalização são fórmulas simples derivadas das contagens exportadas.

## Compatibilidade

Nenhuma migration é necessária. `SCHEMA_VERSION = 29` permanece válido. O endpoint é aditivo e não modifica os contratos existentes de dashboard, metas, planos, sincronização ou legado.
