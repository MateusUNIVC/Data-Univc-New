# DPE-04 - Consolidação do domínio

A versão 0.13.0-dev.4 estabelece um vocabulário único para a DPE moderna sem reconstruir ainda os módulos de Cursos e Receitas.

## Fonte operacional

O Cost Engine permanece a única fonte operacional da DPE. As entidades canônicas são: Competência, Curso, Contexto do curso, Receita, Despesa, Docente, Atividade docente, Regra de distribuição, Execução de rateio, Resultado, Meta e Plano de ação.

## Gestão

Novas metas e planos devem usar os grupos canônicos `DPE-RESULT`, `DPE-REVENUE`, `DPE-EXPENSE`, `DPE-TEACHING` e `DPE-ALLOCATION`.

`DPE-01`, `DPE-02` e `DPE-03` permanecem no catálogo somente como contrato histórico para medições, importação e Excel anteriores. Novas metas ou planos nesses códigos são rejeitados.

## Migration 044

Antes de remapear metas/planos antigos, a migration preserva as linhas em `dpe_domain_legacy_management_archive`. Pares com equivalência segura são convertidos para o vocabulário novo. A métrica histórica `payroll_on_revenue_3m_pct` não é convertida automaticamente por não possuir equivalente semântico exato.

## Fora do escopo

- remover DPE-01/02/03 do Excel e medições;
- retirar a obrigatoriedade PRESENCIAL;
- simplificar lançamentos de Receita;
- simplificar Despesas/Docência/Rateio.

Essas alterações permanecem nas próximas etapas para evitar misturar consolidação estrutural com mudança de regra de negócio.
