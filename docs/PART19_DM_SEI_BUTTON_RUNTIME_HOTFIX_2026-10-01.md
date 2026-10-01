# Parte 19 — DM SEI Button Runtime Hotfix

Data: 01/10/2026  
Versão: Data UNIVC 0.13.0  
Schema esperado: 51  
Migration nova: não.

## Sintoma

Na tela da Diretoria de Mestrado, os botões **Buscar direto no SEI** e **Analisar XLSX do SEI** recebiam o clique, mas o modal não era aberto.

## Causa raiz

O fluxo antigo possuía o controle `#seiCheckDatesWrap`, relacionado à opção de aproveitar o mesmo acesso ao SEI para consultar datas individuais. Esse controle foi corretamente removido quando a atualização de datas/titulação passou a ser uma segunda etapa, desacoplada da sincronização das turmas.

Entretanto, `openSeiModal()` ainda executava:

```javascript
$('#seiCheckDatesWrap').classList.toggle(...)
```

Como o elemento não existia mais no `dm.html`, o navegador lançava uma exceção antes de executar `openModal('seiModal')`. O resultado era um botão visualmente normal, porém aparentemente sem ação.

## Correção

- removida a referência obsoleta `seiCheckDatesWrap` de `dm.js`;
- mantido intacto o novo fluxo em duas etapas do SEI;
- alterado `DM_ASSET_VERSION` para `0.13.0-dmq04b`, forçando atualização do asset no navegador;
- adicionada auditoria automática no preflight para localizar dereferências diretas de IDs inexistentes no template DM;
- adicionados testes específicos para os contratos dos botões SEI.

## Validação de runtime

Além de `node --check`, foi executada validação em Chromium headless com o DOM real da tela DM. Foram confirmados:

- **Buscar direto no SEI** → modal SEI abre;
- **Analisar XLSX do SEI** → modal SEI abre no modo upload;
- **Importar Turmas** → modal de importação abre;
- nenhuma exceção de runtime durante esses cliques.

## Banco de dados

Nenhuma alteração de banco nesta parte. O schema permanece em **51**.

## Regressão

- 250 testes aprovados;
- 2 ignorados;
- 28/28 arquivos JavaScript válidos;
- release checks completos aprovados.
