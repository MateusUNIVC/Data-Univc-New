# DM Students & Defenses Simplification — v0.8.30.0

## Objetivo

Alinhar a experiência operacional de alunos da Diretoria de Mestrado ao domínio consolidado na v0.8.29.0: a defesa é o marco acadêmico ativo de conclusão, sem exigir uma segunda Data de Titulação na interface.

## Mudanças

- a seção passa a se chamar **Alunos e defesas**;
- a coluna **Titulação** foi removida da tabela ativa;
- `studentGraduation`, `graduationCommonDate` e campos individuais de titulação saíram dos formulários;
- registrar `defense_date` atualiza visualmente o status para `Titulado` e o backend mantém a regra já consolidada;
- o fluxo em lote continua permitindo confirmação histórica sem data conhecida, mas não cria data fictícia;
- `graduation_date` e `diploma_status` continuam persistidos para auditoria/compatibilidade e são preservados em edições que não os enviam;
- filtros ativos: ingresso pendente, titulado sem defesa, defesa registrada e defesa marcada;
- busca por nome/matrícula vem primeiro e ocupa maior espaço;
- paginação adiciona primeira/última página e mostra página/faixa/total.

## Compatibilidade

Os filtros legados `graduation_missing` e `graduation_present` continuam aceitos no repositório para clientes antigos, mas não são exibidos na UI. Endpoints de titulação são mantidos internamente nesta etapa para compatibilidade; a experiência visível passa a ser centrada em defesa.

## Banco

Nenhuma migration nova. `SCHEMA_VERSION = 32`.
