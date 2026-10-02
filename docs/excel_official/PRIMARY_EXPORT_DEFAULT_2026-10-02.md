# Excel Official — exportação principal em todas as diretorias

Data: 2026-10-02  
Schema: 53  
Migration: nenhuma

## Estado final

O Excel Oficial passa a ser o engine padrão de exportação em todas as diretorias com workbook oficial concluído:

- DTNH / DCS: `ACADEMIC_EXCEL_OFFICIAL_ENABLED=true` por padrão; `/api/excel` e a rota de compatibilidade acadêmica entregam Excel Oficial.
- DM: `DM_EXCEL_OFFICIAL_ENABLED=true` por padrão; `/api/dm/excel` entrega Excel Oficial.
- DADM: `DADM_EXCEL_OFFICIAL_ENABLED=true` por padrão; `/api/dadm/excel` entrega Excel Oficial.
- DPE: `DPE_EXCEL_OFFICIAL_ENABLED=true` por padrão; `/api/dpe/excel` entrega Excel Oficial.

As flags permanecem por segurança, porém o valor `false` agora significa **rollback explícito de emergência**, e não mais o comportamento normal da aplicação.

## Interface

Os botões normais de exportação continuam apontando apenas para as rotas canônicas. A UI reflete o engine selecionado e, no estado normal/default, exibe `Excel Oficial` / `Baixar Excel Oficial`.

## Reitoria

A Reitoria não mantém um workbook próprio de diretoria nesta etapa. Ao operar os módulos acadêmicos/diretoriais, utiliza as mesmas rotas canônicas e, portanto, herda o Excel Oficial como padrão.

## VPS existente

Arquivos `.env.production` já existentes não são sobrescritos por `git pull`. Se um ambiente antigo ainda contiver alguma flag `...=false`, altere explicitamente para `true` antes do recreate do app.
