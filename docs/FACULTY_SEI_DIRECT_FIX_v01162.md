# v0.11.6.2 — Avaliação Docente · correção do acesso direto ao SEI

## Problema

Na v0.11.6.1, `facultyImportButton` chamava `triggerImport()`, e `triggerImport()` executava `facultyImportFile.click()`. Portanto, a ação apresentada como importação do SEI abria o seletor local de arquivos.

## Correção

O fluxo foi dividido em duas ações independentes:

1. **Buscar direto no SEI**
   - autentica em `/api/surveys/sei/login`;
   - pesquisa aplicações em `/api/surveys/sei/evaluations/search`;
   - seleciona a aplicação em `/api/surveys/sei/evaluations/select`;
   - prepara o escopo protegido em `/api/surveys/faculty-student/sei/prepare`;
   - gera e baixa o relatório em `/api/surveys/faculty-student/sei/report/generate`;
   - entrega o arquivo gerado à mesma prévia segura usada pela importação manual.

2. **Usar XLSX/ZIP já baixado**
   - é a contingência manual;
   - somente esta ação dispara o `input[type=file]`.

## Escopo protegido

O backend continua responsável por garantir:

- detalhamento `Disciplina/Professor`;
- unidade `Graduação (São Mateus-ES)`;
- turno `TODOS`;
- todas as perguntas;
- questionário identificado semanticamente como discente/aluno avaliando docente/professor.

## Segurança

As credenciais são enviadas somente para criar a sessão temporária do conector SEI. Elas não são persistidas no Data UNIVC. A sessão permanece sob o mecanismo temporário já existente, com expiração automática.

## Banco

Nenhuma alteração de schema. A versão permanece compatível com **schema 40**.
