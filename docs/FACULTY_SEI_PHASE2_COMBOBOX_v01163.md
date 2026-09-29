# v0.11.6.3 — Avaliação Docente · segunda geração SEI + comboboxes pesquisáveis

## Objetivo

Corrigir o fluxo direto da Avaliação Docente no SEI até o ZIP final e melhorar a navegação dos filtros com muitos cursos, disciplinas e docentes.

## Correção do fluxo SEI

O HAR real mostrou que o relatório `Disciplina/Professor` possui duas fases independentes:

1. `form:botaoGerarRelatorioEmExcel` prepara a relação de relatórios;
2. após o primeiro `statusPanelBaixa_oncomplete2`, o SEI renderiza `formQuestionarioSelecionar`;
3. o botão global `formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4` inicia a geração efetiva dos XLSX;
4. um segundo ciclo `pool2 → encerrar → oncomplete2` conclui o pacote;
5. somente então aparece `DownloadRelatorioSV?...zip`.

A v0.11.6.2 encerrava o fluxo após a etapa 2 e esperava incorretamente que o ZIP já existisse.

A v0.11.6.3:

- preserva o primeiro ciclo existente;
- reconhece o formulário intermediário;
- diferencia o botão global dos botões individuais de cada curso;
- serializa os campos reais do `formQuestionarioSelecionar`;
- executa a segunda geração;
- acompanha o segundo ciclo de processamento;
- baixa somente após o SEI informar `DownloadRelatorioSV`;
- mantém compatibilidade com fluxos que eventualmente entreguem o arquivo já na primeira fase.

A requisição da segunda fase foi conferida contra o HAR fornecido e coincide nos campos relevantes, inclusive:

- `formQuestionarioSelecionar`;
- `formQuestionarioSelecionar:questionarioRelVOs:j_idt290`;
- `formQuestionarioSelecionar:questionarioRelVOs:j_idt300`;
- `javax.faces.source`;
- `javax.faces.partial.event`;
- `javax.faces.partial.execute`;
- `javax.faces.partial.render`;
- `org.richfaces.ajax.component`;
- `rfExt`;
- `AJAX:EVENTS_COUNT`;
- `javax.faces.partial.ajax`.

## Comboboxes pesquisáveis

Os filtros de **Curso**, **Disciplina** e **Docente** continuam usando o `select` original como fonte de estado, mas recebem uma camada de combobox pesquisável.

Comportamentos:

- pesquisa por texto;
- busca sem diferenciar acentos ou maiúsculas/minúsculas;
- navegação por `ArrowUp` / `ArrowDown`;
- seleção por `Enter`;
- fechamento por `Esc`;
- ação para limpar a seleção;
- filtros continuam encadeados pela API já existente;
- Curso restringe as disciplinas/docentes disponíveis no recorte;
- Disciplina e Docente continuam reconciliados contra os facets reais do backend.

A abordagem preserva o `select` nativo internamente para reduzir risco de regressão na lógica dos filtros.

## Banco

Nenhuma migration nova. O schema permanece **40**.

## QA

- testes da v0.11.1 até v0.11.6.2 preservados;
- 4 testes novos da v0.11.6.3;
- 30/30 testes automatizados aprovados;
- sintaxe Python e JavaScript validada;
- payload da segunda geração comparado diretamente com o HAR real enviado para homologação.
