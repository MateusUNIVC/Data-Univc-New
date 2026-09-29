# v0.11.6.4 — Academic Results Import Hardening

## Objetivo

Reduzir o risco de OOM/restart do servidor ao importar aprovação/resultados acadêmicos em grande volume, principalmente em ambientes de 1 GB de RAM.

## Mudanças

- O relatório bruto do SEI passa por uma primeira leitura de inspeção com `openpyxl` em `read_only=True`.
- Os vínculos aluno-disciplina são produzidos por iterador; o XLSX completo não é materializado em uma lista antes da importação.
- Resultados são persistidos em lotes configuráveis por `ACADEMIC_RESULT_IMPORT_BATCH_SIZE` (padrão: 500; mínimo 100; máximo 2000).
- Cada lote é confirmado separadamente e o cache de matrículas é descartado entre lotes, limitando o crescimento de RAM.
- Reimportação continua idempotente pela chave semestre + curso + disciplina + aluno + turma.
- A sincronização SEI da interface processa os cursos sequencialmente, um request por curso, preservando os cursos já concluídos se outro falhar.
- O endpoint direto do SEI é síncrono para o FastAPI, portanto roda no thread pool e não bloqueia o event loop/health check.
- Upload manual de Resultados também desloca o processamento pesado para thread pool com sessão SQL própria.
- O modelo padronizado `Modelo_Resultados_Academicos.xlsx` também passa a ser importado em lotes.
- Nenhuma migration nova; schema permanece 40.

## Retomada após falha

Não foi criada uma nova tabela de job. A retomada usa a idempotência existente: basta executar novamente o(s) curso(s) afetado(s). Lotes já confirmados aparecem como duplicados e não são recriados. Essa abordagem evita aumentar o schema e mantém a operação simples.

## Validação local

Um XLSX sintético com 10.000 vínculos aluno-disciplina foi importado em 20 lotes de 500. No ambiente de validação:

- v0.11.6.3 (importação monolítica): pico RSS aproximado de 217 MB;
- v0.11.6.4 (streaming + lotes): pico RSS aproximado de 158 MB;
- redução aproximada observada: 27%.

Esse benchmark é sintético e serve apenas para comparar as duas arquiteturas no mesmo ambiente; não representa garantia de consumo em produção.

## Deploy

Schema esperado: **40**. Não há migration nova.

Variável opcional:

```env
ACADEMIC_RESULT_IMPORT_BATCH_SIZE=500
```

Para VPS de 1 GB, mantenha 500 inicialmente. Só aumente após observar memória e duração das cargas reais.
