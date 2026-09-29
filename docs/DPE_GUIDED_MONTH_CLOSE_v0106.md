# DPE v0.10.6 — Fechamento Guiado

## Objetivo

Transformar o fechamento mensal em uma decisao orientada ao usuario, sem expor como fluxo principal os detalhes tecnicos de versionamento, fingerprint, conciliacao e eventos de auditoria.

## Experiencia principal

A tela responde primeiro se o mes esta pronto para ser fechado. O estado pode ser pendente, pronto ou fechado.

O checklist principal e composto por cinco etapas de negocio:

1. Cursos do mes;
2. Despesas;
3. Docentes e folha;
4. Alunos e receitas;
5. Distribuicao de custos.

Cada etapa pendente possui uma acao direta para a area onde a correcao deve ser feita.

## Pendencias

A lista de atencao utiliza as pendencias executivas ja deduplicadas pelo `v2-overview`. Assim, causas tecnicas derivadas do mesmo problema nao aparecem como varios erros independentes.

Exemplos de direcionamento:

- folha nao conciliada -> Docentes / Folha docente;
- alunos ou receita ausentes -> Cursos / Alunos e receitas;
- lote de importacao pendente -> Despesas / Importacoes;
- distribuicao desatualizada -> Distribuicao de custos.

## Detalhes sob demanda

Versao oficial do calculo, checklist tecnico completo e historico de fechamentos/reaberturas permanecem disponiveis em `Ver detalhes do fechamento e auditoria`.

## Governanca preservada

As regras de fechamento e reabertura nao foram alteradas. Um mes so pode ser fechado quando o backend informa `can_close=true`. Reabrir continua exigindo justificativa e gera evento permanente de auditoria.

## Banco

Nenhuma migration nova. Schema 39 permanece canonico.
