# DADM V2 Reporting UI Integration — v0.8.23.2

## Objetivo

Conectar o motor XLSX agregado introduzido na v0.8.23.1 ao contexto real de uso da DADM, sem duplicar filtros e sem iniciar nesta etapa o pacote de animações ou calendários.

## Topbar

A topbar da DADM passa a seguir a mesma hierarquia de produto usada nas diretorias acadêmicas:

1. título da diretoria e página atual;
2. `Diretoria em visualização` com seletor e badge de acesso na mesma linha;
3. estado da integração TALLOS;
4. ação `Gerar relatório`.

Nenhum controle anterior foi removido. Em telas menores, o seletor é preservado e a ação de relatório reduz o rótulo para manter a composição compacta.

## Contrato do relatório

O frontend não mantém estado próprio para relatórios. O download usa diretamente:

```javascript
NS.filterParams(state.filters)
```

Portanto o recorte do XLSX é exatamente o mesmo da análise web:

- `from_month`;
- `to_month`;
- `department`;
- `employee`;
- `channel`;
- `status`;
- `tabulation`.

O botão permanece desabilitado somente enquanto o período inicial ainda não foi resolvido pelo contexto analítico.

## Confirmação antes do download

O modal exibe período, departamento, operador, canal, status e tabulação. Valores não filtrados aparecem como `Todos`/`Todas`, deixando explícito o escopo antes da geração.

O modal também informa que o arquivo é agregado e não contém atendimento individual ou dado pessoal de cliente.

## Download

A geração usa `fetch` autenticado com `same-origin`, recebe o XLSX como `Blob` e utiliza `Content-Disposition` para preservar o nome de arquivo definido pelo backend. Respostas 401 levam ao fluxo de login e demais erros são apresentados no alerta padrão da DADM.

A operação é de leitura e, por isso, não recebe `data-write-action` nem depende de `canWrite()`.

## Fora de escopo desta etapa

Permanecem para os prompts seguintes:

- animação de recolhimento/expansão da sidebar;
- motion system dos cards, filtros, modais e gráficos;
- comportamento explícito dos ícones de calendário em Dados & Integração.

## Banco

Não há alteração de schema. O Data UNIVC continua em `SCHEMA_VERSION = 29`.
