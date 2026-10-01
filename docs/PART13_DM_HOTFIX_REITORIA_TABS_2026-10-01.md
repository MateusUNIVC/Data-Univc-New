# Parte 13 — Hotfix DM + reconstrução acadêmica da Reitoria

Data: 2026-10-01
Versão: 0.13.0
Schema: 49 (sem nova migration)

## 1. Diretoria de Mestrado — blocos fragmentados do SEI

O relatório real do SEI pode dividir a mesma turma lógica em mais de um bloco físico. Exemplo validado no relatório `1790874693805.xlsx`:

- `17-CTE` — 50 alunos;
- `17-CTE Mestrado Univc` — 1 aluno;
- ambos representam `CTE:17`.

O parser anterior tratava a segunda ocorrência da mesma área + número de turma como `Bloco duplicado` e interrompia a importação.

A Parte 13 consolida esses fragmentos quando são seguros:

- blocos não-teste da mesma área + número são unidos;
- alunos distintos são preservados;
- linhas idênticas repetidas da mesma matrícula são deduplicadas;
- conflito de dados da mesma matrícula continua bloqueando a importação;
- matrícula repetida em turmas lógicas diferentes continua bloqueando;
- colisão entre turma real e TESTE/DEMO/HOMOLOGAÇÃO continua bloqueada.

Validação no arquivo real fornecido:

- 13 turmas lógicas;
- 433 alunos;
- `CTE:17` consolidada com 51 alunos;
- `CTE:1` identificada como turma de teste com 2 alunos;
- ao ignorar turmas de teste, o recorte esperado é 12 turmas e 431 alunos.

## 2. Reitoria — painel acadêmico reconstruído

A visão acadêmica deixa de ser um bloco empilhado no meio da administração da Reitoria. A página passa a ter navegação por telas independentes, no mesmo princípio visual de DTNH/DCS.

### Painel acadêmico

- `NPS`
- `Avaliação Docente`
- `Notas e Aprovação`

### Administração separada

- `Visão geral`
- `Usuários e acessos`
- `Auditoria`

Somente a tela ativa é exibida. O painel acadêmico abre por padrão em `#nps`.

### NPS

- NPS da Instituição · Alunos;
- NPS dos Cursos;
- NPS da Instituição · Docentes;
- evolução histórica;
- comparação de todos os cursos de DTNH/DCS;
- distribuições 0–10.

O filtro de disciplina fica oculto nesta aba porque NPS não possui granularidade por disciplina.

### Avaliação Docente

- favorabilidade;
- participações classificadas;
- evolução por semestre;
- comparação por curso;
- filtros por diretoria, curso e disciplina.

Turmas compartilhadas continuam deduplicadas no total institucional.

### Notas e Aprovação

- taxa de aprovação;
- média das notas;
- alunos distintos;
- evolução da aprovação;
- evolução da média;
- evolução de alunos;
- aprovação por curso.

As escalas semânticas permanecem: aprovação 0–100%, notas 0–10 e contagens com mínimo zero.

## 3. Backend

A lógica institucional da Parte 12 foi preservada. A agregação continua feita pelas contagens-base, sem média simples entre DTNH e DCS.

Os endpoints continuam protegidos por `require_fresh_reitoria` e a visão acadêmica continua somente leitura.

## 4. Validação

- 229 testes aprovados;
- 2 testes ignorados;
- 28/28 JavaScripts válidos;
- 28/28 referências JavaScript nos templates presentes;
- arquivo real do Mestrado validado;
- sem migration nova;
- schema 49 preservado.
