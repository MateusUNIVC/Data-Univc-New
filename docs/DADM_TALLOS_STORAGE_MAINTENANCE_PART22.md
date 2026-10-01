# Parte 22 — DADM/TALLOS · benchmark e manutenção de armazenamento

## Objetivo

Concluir `TALLOS-COMPACT-05` depois da retirada do payload bruto feita nas Partes 20 e 21. Esta etapa não altera schema nem KPIs. Ela cria uma rotina operacional repetível para medir o armazenamento, confirmar que o payload permaneceu aposentado e executar manutenção PostgreSQL com níveis de risco explícitos.

## Auditoria

Execute:

```bash
scripts/tallos_storage_maintenance.sh audit
```

O relatório mostra:

- tamanho do heap da tabela `dadm_tallos_attendances`;
- tamanho dos índices;
- tamanho de TOAST/estruturas auxiliares;
- tamanho total da relação;
- quantidade de atendimentos e footprint lógico médio por linha;
- quantidade e bytes de payload residual diferente de `{}`;
- saúde do contrato compacto (`rating_source_state`, `normalization_version`, `source_hash`);
- distribuição dos estados da avaliação;
- versões de normalização presentes;
- tuplas vivas/mortas e últimos VACUUM/ANALYZE;
- cobertura temporal da base TALLOS.

Após a migration 053 e um sync com a Parte 21+, o resultado saudável é `rows_with_payload = 0`. Não é esperado que o arquivo físico da tabela diminua imediatamente só porque os JSONs foram substituídos por `{}`.

## VACUUM normal

Execute:

```bash
scripts/tallos_storage_maintenance.sh vacuum
```

Isso executa `VACUUM (ANALYZE, VERBOSE)` e depois repete a auditoria. É a opção padrão após a limpeza histórica. Ela atualiza estatísticas e torna espaço morto reutilizável pelo PostgreSQL, sem reescrever toda a tabela.

## VACUUM FULL

Use apenas quando houver necessidade concreta de devolver espaço ao sistema operacional e em janela de manutenção.

```bash
CONFIRM_TALLOS_VACUUM_FULL=YES scripts/tallos_storage_maintenance.sh vacuum-full
```

A proteção é intencional: `VACUUM FULL` reescreve a tabela e requer `ACCESS EXCLUSIVE`, portanto consultas/escritas que dependam de `dadm_tallos_attendances` podem bloquear até o término.

## Sequência recomendada de produção

1. aplicar/confirmar schema 53;
2. garantir que a aplicação Parte 21+ esteja no ar;
3. executar `audit` e salvar a saída;
4. confirmar `rows_with_payload = 0`;
5. validar os KPIs da DADM/TALLOS na interface;
6. executar `vacuum`;
7. executar `audit` novamente;
8. somente se o tamanho físico continuar sendo um problema operacional, agendar `vacuum-full`;
9. após `vacuum-full`, executar a auditoria uma terceira vez e comparar o tamanho total.

## Critério de encerramento do bloco Tallos

O bloco de compactação é considerado concluído quando:

- nenhum analytics lê `source_payload_json`;
- novas ingestões não persistem payload;
- `rows_with_payload = 0` no histórico;
- `rating_source_state`, `normalization_version` e `source_hash` estão íntegros;
- reimportação continua idempotente;
- os KPIs antes/depois permanecem equivalentes;
- existe rotina reproduzível de medição e manutenção.
