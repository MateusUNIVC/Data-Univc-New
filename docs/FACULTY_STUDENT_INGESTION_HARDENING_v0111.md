# v0.11.1 — Avaliação Docente pelo Discente · Ingestão endurecida e importação segura

## Objetivo

A v0.11.1 estabiliza a fundação criada na v0.11.0 antes da construção da camada analítica. O foco é garantir que o ZIP real do SEI seja classificado, validado e reimportado sem perda de escopo ou duplicação de contextos.

Nenhuma tela analítica nova é introduzida nesta release. O KPI 02 legado continua ativo até a etapa de analytics/frontend.

## Correção crítica do ZIP real

O ZIP real de 24/09/2026 usa no diretório da Graduação a forma:

`CENTRO_UNIVERSITARIO_VALE_DO_CRICARE__GRADUACAO_(SAO_MATEUSES)`

Enquanto o XLSX identifica a unidade como:

`CENTRO UNIVERSITÁRIO VALE DO CRICARÉ - GRADUAÇÃO (SÃO MATEUS-ES)`

Na v0.11.0, a diferença `SAO_MATEUSES` x `SÃO MATEUS-ES` fazia a barreira rápida rejeitar todos os XLSX antes da abertura.

A v0.11.1 usa equivalência estrita por conteúdo normalizado e compactado para tolerar apenas diferenças de acento, pontuação e separadores. `GRADUAÇÃO SEMIPRESENCIAL`, polos, cursos técnicos e demais unidades continuam diferentes e fora do escopo.

## Caminho é pista; conteúdo é autoridade

O fast reject do ZIP passa a ser conservador:

- caminhos que identificam explicitamente `SEMIPRESENCIAL`, `POLO`, `CURSOS TÉCNICOS` ou `PÓS-GRADUAÇÃO` podem ser descartados sem abrir o XLSX;
- Graduação São Mateus é aberta e validada pelo conteúdo;
- caminhos desconhecidos/ambíguos também são abertos, em vez de rejeitados por aproximação;
- antes da importação, a unidade gravada dentro do XLSX é novamente validada.

O preview informa quantos XLSX foram abertos, quantos foram validados pelo conteúdo, quantos foram rejeitados de forma segura pelo caminho e se houve divergência caminho x conteúdo.

## Validação com o lote real

No arquivo `AVAL_INST_77_1790289633381.zip` usado para homologação:

- 737 XLSX encontrados;
- 603 pertencem à Graduação São Mateus;
- 603 XLSX da Graduação foram abertos e interpretados;
- 134 foram rejeitados de forma segura por pertencerem a outras unidades;
- 0 erros de parser entre os 603 XLSX da Graduação;
- todos os 603 relatórios possuem 9 perguntas;
- todos usam o questionário `Avaliação Institucional discente 2023.2 - aluno avalia professor`;
- nenhum dos 603 informa explicitamente `2026.1`/`2026.2` no título, portanto a confirmação de semestre continua obrigatória para uma nova importação.

Com os catálogos presenciais atuais, o lote contém 137 contextos compatíveis com DTNH e 179 compatíveis com DCS. Os demais permanecem fora do escopo de cada diretoria ou exigem resolução de identidade.

## Semestre

A normalização aceita formas explícitas como:

- `2026.1`;
- `2026-1`;
- `2026/1`;
- `2026-SEM1`;
- equivalentes para `SEM2`.

O sistema não infere semestre a partir de julho ou de qualquer outra data da aplicação.

O preview passa a distinguir:

- uma sugestão explícita única;
- ausência de semestre, exigindo confirmação;
- múltiplos semestres explícitos, exigindo escolha manual;
- semestre já vinculado a uma importação anterior da mesma avaliação.

## Educação Física

`Educação Física` sem habilitação não é convertido automaticamente.

No DCS, o preview retorna resolução manual obrigatória e apresenta como candidatos:

- `Educação Física - Bacharelado`;
- `Educação Física - Licenciatura`.

Rótulos explícitos como `Educação Física (Bac. Presencial)` continuam resolvidos pelos aliases institucionais existentes.

## Idempotência reforçada

A v0.11.0 já impedia duplicação quando a mesma fonte era processada novamente. A v0.11.1 reforça essa regra em dois níveis:

1. **Identidade do lote**
   - usa a chave externa do SEI quando disponível;
   - usa SHA-256 quando o arquivo é exatamente o mesmo;
   - para uploads manuais regenerados, procura uma avaliação existente pela identidade lógica do questionário, título, período e semestre.

2. **Identidade do contexto acadêmico**
   - dentro de um mesmo `survey_run`, uma atribuição docente `semestre + curso + disciplina + professor` só possui um contexto de avaliação;
   - o ID interno/nome do XLSX não é mais necessário para impedir duplicação;
   - uma reexportação do SEI com novo report ID não cria uma segunda distribuição de respostas.

O preview também informa quantos contextos da mesma fonte já estão persistidos e marca essas linhas como `already_imported`.

## Novos estados do preview

Além dos estados da v0.11.0, o preview pode retornar:

- `already_imported` — contexto já persistido na mesma avaliação;
- `course_out_of_scope` com `resolution_required=true` — identidade do curso precisa ser resolvida antes de importar.

O resumo inclui:

- total de relatórios;
- elegíveis;
- já importados;
- cursos, professores e disciplinas elegíveis;
- respostas por contexto;
- fora da unidade;
- fora do catálogo/modalidade;
- pendências de identidade do curso;
- questionário incorreto;
- relatório inválido;
- XLSX abertos/validados/rejeitados pelo fast reject.

## Persistência e compatibilidade

- nenhuma migration nova;
- schema permanece em 39;
- tabelas `teachers`, `academic_offerings`, `teaching_assignments`, `faculty_evaluation_contexts`, `faculty_response_aggregates` e `faculty_raw_responses` permanecem a fonte relacional da nova avaliação;
- KPI 02 legado e `teacher_evaluations` continuam intactos;
- fluxos NPS e `faculty-institution` não são alterados.

## Testes adicionados

`tests/test_faculty_student_v0111.py` cobre:

- equivalência do nome real da pasta da Graduação;
- rejeição de Graduação Semipresencial;
- validação explícita de semestre;
- ambiguidade de Educação Física;
- reimportação manual com SHA e report ID diferentes sem duplicar contexto.

O utilitário `scripts/verify_faculty_student_v0111.py` permite inspecionar um ZIP/XLSX do SEI sem persistir dados.

## Próxima etapa

Com a ingestão estabilizada, a v0.11.2 pode iniciar a camada de normalização/qualidade acadêmica e preparar o motor analítico por semestre, curso, disciplina, professor e pergunta. A interface definitiva do KPI 02 continua posterior a essa camada.
