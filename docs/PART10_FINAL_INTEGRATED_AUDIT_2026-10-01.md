# Parte 10 — Auditoria final integrada · 01/10/2026

Esta etapa fecha a sequência de melhorias acadêmicas sem criar um novo domínio funcional ou uma nova migration. O objetivo é garantir coerência entre regras, gráficos, metas, Excel e artefato de produção.

## Ajustes finais aplicados

- metas acadêmicas de NPS (01A/01B/01C) passam a aceitar somente valores entre -100 e +100;
- metas de favorabilidade docente (02) e taxa de aprovação (03) passam a aceitar somente 0–100%;
- para os indicadores acadêmicos em que maior é melhor, o limiar de atenção não pode ficar acima da meta;
- quando informado, o limite superior não pode ficar abaixo da meta;
- o formulário de metas aplica os mesmos limites com `min`/`max` e informa o domínio válido ao usuário;
- o gráfico Excel de Promotores/Neutros/Detratores passa a ter eixo fixo 0–100%, alinhado à web;
- removida uma chave duplicada inofensiva do catálogo `DTNH-01C`;
- o release check agora exige explicitamente `dpe_cost_v2.py`, os JavaScripts acadêmicos ativos e a migration canônica 049;
- o release check também verifica os helpers ativos do bootstrap, incluindo `fillConfig`, antes de executar a suíte.

## Invariantes auditadas

- Taxa de aprovação: 0–100%;
- Favorabilidade docente: 0–100%;
- NPS: -100 a +100;
- Contagens de alunos: mínimo visual zero;
- Distribuição NPS: notas 0–10 e soma das contagens igual ao número de respostas classificáveis da distribuição;
- turmas compartilhadas: um contexto de respostas, múltiplos escopos de curso, sem duplicação global;
- Educação Física: regra específica do SEI atual preservada;
- Excel Interativo: 5 gráficos executivos, bases gerenciais visíveis, camada técnica oculta;
- schema: 49, migration `049_academic_faculty_context_scopes_v0130.sql`.

## Resultado da regressão

- Pytest: 207 aprovados, 2 ignorados;
- JavaScript: 26/26 válidos com `node --check`;
- referências JavaScript em templates: 26/26 presentes;
- Python compile: OK;
- release checks: OK;
- sem migration nova.

## Deploy

Se o PostgreSQL já está no schema 49:

```bash
cd /opt/data-univc
git pull
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
docker compose logs --tail=100
```

Se o schema ainda não estiver em 49, aplicar primeiro `database/049_academic_faculty_context_scopes_v0130.sql` em transação e confirmar o ledger antes de recriar a aplicação.

## Rollback

O rollback de código pode ser feito retornando ao commit imediatamente anterior e reconstruindo o container. A migration 049 é aditiva e deve permanecer aplicada; não é necessário desfazê-la para voltar a uma versão de código desta mesma linha que já suporte schema 49.
