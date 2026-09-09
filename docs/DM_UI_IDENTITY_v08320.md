# DM — UI Identity & Topbar Convergence — v0.8.32.0

## Objetivo

Remover a camada visual paralela da topbar da Diretoria de Mestrado e fazer a DM consumir diretamente a mesma fundação `ui-v2` utilizada por DTNH/DCS, preservando todas as ações funcionais existentes.

## Topbar

A DM mantém, na mesma ordem lógica da fundação acadêmica:

1. código da diretoria e título da página;
2. `Diretoria em visualização` + badge Edição/Somente leitura;
3. estado `Banco sincronizado`;
4. ação SEI;
5. Exportar;
6. Nova Turma.

O CSS específico da DM deixa de redefinir `directorate-switcher`, label, select e breakpoints da topbar. Essas decisões passam a pertencer a `ui-v2.css`.

## Cabeçalhos de página

DM-01, DM-02, Turmas e Alunos usam o ritmo `compact-lead`, aproximando espaçamento, hierarquia tipográfica e responsividade das páginas acadêmicas.

## Compatibilidade

- nenhuma API alterada;
- nenhuma regra de permissão alterada;
- nenhuma ação removida;
- nenhuma migration nova;
- `SCHEMA_VERSION = 32`.
