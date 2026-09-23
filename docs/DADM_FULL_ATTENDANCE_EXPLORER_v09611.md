# Data UNIVC v0.9.6.11 - DADM Full Attendance Explorer

## Objetivo
Pessoas & Setores passa a investigar todos os atendimentos Tallos que compoem TME/TMA, e nao somente sessoes avaliadas.

## Funcionalidades
- Todos os atendimentos por operador ou departamento.
- Filtros: Todos, Com avaliacao, Sem avaliacao.
- Ordenacoes: mais recentes, mais antigos, maior TME, maior TMA, menor nota e maior nota.
- Departamentos mostram o operador responsavel em cada sessao.
- A sessao Tallos (source_id) continua sendo a unidade; nao ha deduplicacao por protocolo.
- Sessoes sem nota exibem Sem avaliacao, sem converter ausencia em zero.
- O endpoint legado /api/dadm/v2/entity/evaluations permanece rated-only para compatibilidade.
- Nenhum dado pessoal do atendido ou source_payload_json e enviado ao frontend.
- allowed_departments continua aplicado no SQL.

## Banco e producao
- Schema 33.
- Nenhuma migration nova.
- Nenhuma mudanca na sincronizacao Tallos.
- Nenhum Cron Job.
- Mesmo Supabase/PostgreSQL e mesmo Web Service Render.
