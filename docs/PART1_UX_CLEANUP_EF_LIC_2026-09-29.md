# Parte 1 - limpeza de UX e compatibilidade Educação Física - Licenciatura

Data: 2026-09-29
Versão de aplicação: 0.13.0
Schema: 48 (sem migration)

## Escopo implementado

### Resultados Acadêmicos
- removido da interface o alerta de alunos sem resultado classificável;
- removida a mesma informação do tooltip de alunos distintos;
- mantidos no backend os campos e a classificação técnica de registros sem situação final;
- nenhum aluno é convertido artificialmente em aprovado ou reprovado.

### Avaliação Docente
- removido o painel superior de diagnóstico operacional (Cobertura classificada, Prontidão, Participações, Docentes, Disciplinas, Contextos, Qualidade e Última importação);
- removidos os cards e detalhes de qualidade/identidade da aba de importações;
- a aba passa a se chamar apenas `Importações`;
- a API de qualidade deixa de ser carregada pela tela, mas as verificações do backend permanecem disponíveis para diagnóstico técnico;
- mantidos os avisos que alteram a validade do próprio indicador, como categoria de resposta ainda não mapeada.

### Educação Física - Licenciatura
A seleção de curso no SEI não havia mudado entre a versão antiga analisada e a base atual: `academic_catalog.py` é idêntico e a alteração relevante em `sei_academic.py` foi a migração do parser materializado para o parser streaming.

A regressão encontrada estava na validação posterior do XLSX. A versão antiga comparava as habilitações usando os cursos presentes nos registros efetivos de alunos. O parser streaming passou a expor para essa validação todos os rótulos `Curso:` encontrados nos blocos, inclusive blocos vazios/auxiliares. Um bloco vazio com o rótulo genérico `Educação Física` podia, portanto, bloquear um relatório válido de Licenciatura.

A correção mantém o parser streaming e separa:
- `cursos_de_blocos`: todos os rótulos encontrados, para diagnóstico;
- `cursos_encontrados`: somente cursos de blocos que efetivamente produziram registros de alunos, usado na validação de identidade.

A proteção contra mistura real de Bacharelado e Licenciatura continua ativa: blocos com alunos de uma habilitação diferente continuam participando da validação.

## Não incluído nesta parte
- combobox pesquisável de disciplinas;
- ano + semestre em inputs separados;
- nomes longos no gráfico de NPS;
- otimização em lote de Avaliação Docente/NPS;
- remodelagem do Excel Interativo;
- limpeza geral de frontend legado.

## Validação
- `node --check static/js/app.js`: OK
- `node --check static/js/faculty-evaluation.js`: OK
- compilação Python do parser modificado: OK
- suite completa: 163 passed, 2 skipped
- teste de regressão específico para Educação Física - Licenciatura incluído.


## Hotfix SEI — Educação Física - Licenciatura (29/09/2026)

O HAR capturado em produção confirmou uma mudança no rótulo do curso no SEI:

- Bacharelado permanece como `Educação Física (Bac. Presencial)`.
- Licenciatura passou a aparecer como `Educação Física`.
- A seleção validada no HAR usa a configuração ativa `INTEGRAL - NOTURNO`.
- Após a seleção, `form:nomeCurso` também fica como `Educação Física`.
- O XLSX real capturado traz `Curso: Educação Física`.

A correção mantém o nome institucional `Educação Física - Licenciatura` no Data UNIVC e cria uma compatibilidade específica do fluxo SEI. O rótulo genérico `Educação Física` não virou alias institucional global: sem `expected_course` explícito ele continua bloqueado como ambíguo.

Validação com o XLSX real extraído do HAR: 150 registros lidos, 150 inseridos em banco de teste e todos persistidos sob `Educação Física - Licenciatura`.
