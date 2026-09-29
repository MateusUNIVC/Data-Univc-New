# Parte 2 — filtros pesquisáveis de disciplina

Data: 29/09/2026

## Escopo

- Visão Geral acadêmica: filtro de disciplina convertido para combobox pesquisável.
- Aprovações e Notas: filtro de disciplina convertido para combobox pesquisável.
- Avaliação Docente: migração do combobox próprio para o componente compartilhado.
- O `<select>` nativo permanece como fonte de verdade; contratos das APIs e listeners `change` não foram alterados.

## Componente compartilhado

Implementado em `static/js/data-univc-ui.js` como `DataUNIVC.searchableSelect`.

Recursos:

- pesquisa sem diferenciar maiúsculas/minúsculas;
- pesquisa sem diferenciar acentos;
- navegação com setas;
- seleção por Enter;
- Escape fecha a lista;
- botão de limpeza;
- sincronização após reconstrução dinâmica das opções;
- estado desabilitado quando nenhum curso foi selecionado;
- rótulos longos quebram linha no menu em vez de serem cortados;
- comportamento responsivo.

## Compatibilidade

Nenhuma migration. Nenhuma alteração de API. DTNH e DCS compartilham a mesma implementação.

## Cache de assets

A página acadêmica passou a usar `APP_VERSION + BUILD_FINGERPRINT` na query string dos CSS/JS. Isso evita que navegador/proxy reapresente JavaScript antigo depois de um deploy que mantenha a versão funcional 0.13.0.
