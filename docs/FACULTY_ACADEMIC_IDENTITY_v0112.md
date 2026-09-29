# v0.11.2 — Avaliação Docente pelo Discente · Identidade acadêmica e resolução controlada

## Objetivo

A v0.11.2 continua a reconstrução do KPI 02 sobre a ingestão estabilizada na v0.11.1. O foco desta release é garantir que cada avaliação persistida possua uma identidade acadêmica explicável e estável:

`semestre → curso → disciplina → professor → turma/oferta → contexto de avaliação`.

Nenhuma nota 0–10 nova é calculada e o frontend definitivo do KPI 02 ainda não é substituído nesta etapa.

## Princípio de identidade

A normalização é estrita. O sistema:

- remove apenas diferenças seguras de espaços, acentos, caixa e pontuação para comparação;
- usa aliases institucionais já conhecidos para cursos;
- não usa fuzzy matching, distância de edição nem substrings amplas para decidir identidade;
- não remove sobrenomes, títulos ou partes do nome de docentes;
- não une disciplinas de cursos diferentes apenas porque possuem o mesmo nome.

A nova camada pura está em `survey_faculty_identity.py`.

## Professor, disciplina e oferta

### Professor

`teachers` continua sendo a identidade global do docente. O nome normalizado é reutilizado entre cursos e semestres. Assim, o mesmo professor pode possuir várias atribuições sem criar uma nova pessoa a cada contexto.

### Disciplina

`disciplines` continua vinculada ao curso. Duas disciplinas chamadas `Metodologia Científica` em cursos diferentes permanecem registros diferentes.

### Oferta acadêmica

`academic_offerings` representa:

- semestre;
- curso;
- disciplina;
- turma (`class_group`, quando disponível).

O XLSX atual do SEI é agregado por `Disciplina/Professor` e não informa turma. A identidade já inclui `class_group` de forma opcional para não colapsar turmas caso o SEI passe a informá-las no futuro.

### Atribuição docente

`teaching_assignments` liga uma oferta acadêmica a um professor. Um mesmo professor pode, portanto, estar em várias disciplinas/cursos no mesmo semestre e mudar de vínculo entre semestres sem perder o histórico.

## Resolução explícita de curso

A v0.11.1 detectava `Educação Física` sem habilitação, mas ainda não possuía o contrato completo para resolver a pendência durante a importação.

A v0.11.2 acrescenta esse contrato.

Quando um curso é ambíguo, o preview retorna:

- `scope_status = course_resolution_required`;
- `resolution_key` igual ao caminho interno do XLSX;
- `candidate_ids`;
- `candidate_courses` com `course_id`, nome e modalidade.

A resolução é feita por contexto/arquivo, nunca por alias global. Isso impede que uma decisão tomada para um relatório chamado apenas `Educação Física` contamine todos os relatórios futuros com o mesmo rótulo.

## Proteções da resolução manual

O endpoint de processamento aceita:

```json
{
  "token": "...",
  "selected_paths": [".../200_....xlsx"],
  "semester_override": "2026-SEM1",
  "course_resolutions": {
    ".../200_....xlsx": 123
  }
}
```

O `course_id` só é aceito quando:

1. pertence à mesma diretoria;
2. o preview marcou aquele arquivo como resolvível;
3. o ID está na lista de candidatos permitidos para o relatório;
4. a modalidade é compatível.

Não existe override livre de um curso desconhecido para outro curso arbitrário.

## Auditoria da decisão

As resoluções aplicadas são gravadas nos metadados da importação em `faculty_course_resolutions`, preservando:

- caminho do arquivo;
- `source_key`;
- rótulo bruto do curso;
- `course_id` escolhido;
- nome institucional do curso.

O evento de auditoria da importação também registra a quantidade de resoluções aplicadas.

## Reimportação de contexto ambíguo

Ao inspecionar novamente um ZIP, a v0.11.2 compara cada candidato de um rótulo ambíguo com os contextos já persistidos.

Se exatamente um candidato já tiver sido resolvido/importado para a combinação professor + disciplina + turma, o preview retorna `already_imported` e expõe `existing_resolution`.

Assim, o usuário não precisa resolver a mesma ambiguidade a cada nova exportação do SEI.

## Chave semântica e turma

`faculty_context_semantic_key` passa a considerar também `class_group`.

Nos relatórios atuais o valor é vazio, portanto não há mudança no resultado presente. A alteração evita colisões futuras caso duas turmas da mesma disciplina/professor passem a ser exportadas separadamente.

## API de diagnóstico da identidade

Foram adicionados dois endpoints de leitura para preparar a camada analítica:

### `GET /api/surveys/faculty-student/identity/catalog`

Retorna a malha persistida com:

- semestre;
- curso;
- disciplina;
- professor;
- turma;
- offering;
- teaching assignment;
- contexto;
- respondentes;
- origem.

Aceita `semester=AAAA-SEM1/SEM2`.

### `GET /api/surveys/faculty-student/identity/quality`

Audita a integridade relacional antes do analytics e informa, entre outros:

- contextos duplicados para a mesma atribuição dentro do mesmo run;
- disciplinas que colapsam para a mesma identidade normalizada dentro de um curso;
- contextos sem respondentes;
- docentes sem `external_id`.

A ausência de `external_id` é aviso de rastreabilidade, não erro: o relatório atual do SEI identifica os docentes por nome.

## Validação sobre o lote real

O lote `AVAL_INST_77_1790289633381.zip` permanece com 603 relatórios da Graduação já validados na v0.11.1.

Uma varredura do catálogo da v0.11.2 sobre os rótulos reais confirma:

- DTNH: 137 contextos com curso automaticamente reconhecido;
- DCS: 179 contextos com curso automaticamente reconhecido;
- DCS: 18 contextos `Educação Física` que exigem resolução Bacharelado/Licenciatura;
- demais cursos ficam fora do escopo da diretoria/modalidade correspondente.

Um recorte com XLSX reais confirmou o fluxo completo de `course_resolution_required` e a importação de contexto ambíguo com auditoria.

## Banco e compatibilidade

- schema permanece em `39`;
- nenhuma migration nova;
- `teacher_evaluations` e KPI 02 legado continuam intactos;
- NPS, faculty-institution e demais fluxos acadêmicos não mudam de contrato;
- as novas resoluções são guardadas em `survey_imports.metadata_json`, portanto não exigem tabela adicional.

## Testes

`tests/test_faculty_student_v0112.py` cobre:

- candidatos e IDs permitidos de Educação Física;
- rejeição de resolução para curso de outra diretoria;
- auditoria da resolução manual;
- reutilização do mesmo professor entre cursos e semestres;
- separação de disciplinas homônimas em cursos distintos;
- catálogo e diagnóstico da malha relacional;
- distinção futura por `class_group`.

## Próxima etapa

Com ingestão e identidade acadêmica estabilizadas, a v0.11.3 pode construir o motor analítico sobre `faculty_response_aggregates`, criando consultas por semestre, curso, disciplina, professor e pergunta sem depender do KPI 02 legado.
