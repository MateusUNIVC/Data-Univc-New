# DPE v0.10.5 — Despesas com entrada progressiva

A Central de Despesas passa a separar lançamento, importações e cadastros auxiliares para reduzir carga cognitiva sem alterar o domínio financeiro.

## Objetivos de UX

- mostrar primeiro apenas o que o usuário precisa para registrar um gasto;
- manter origem, integração, referência e observações disponíveis sem ocupar a tela principal;
- separar lançamentos mensais de importações e de cadastros estruturais;
- preservar o critério de distribuição como responsabilidade da área Distribuição de custos;
- reduzir filtros e colunas técnicas na tabela principal.

## Nova organização

A área Despesas possui três visões internas:

1. **Lançamentos** — despesas oficiais do mês, filtros essenciais e novo lançamento;
2. **Importações** — entradas recebidas por Excel/API/requisição antes de virarem despesas oficiais;
3. **Categorias e setores** — cadastros usados para classificar os gastos.

Somente uma dessas visões fica aberta por vez.

## Formulário progressivo

O primeiro nível do formulário mostra:

- descrição;
- valor;
- data;
- categoria;
- setor;
- tipo;
- fornecedor/beneficiário.

Documento, referência de origem e observações ficam em **Informações adicionais**. A origem é preservada automaticamente e não vira uma decisão recorrente do usuário.

O critério de distribuição não é editado nessa tela. A categoria pode sugerir um critério, que é apresentado como orientação e depois pode ser revisado na área **Distribuição de custos**.

## Tabela principal

A tabela mensal foi reduzida para:

- despesa;
- valor;
- categoria;
- setor;
- distribuição;
- ações.

Tipo, data e beneficiário aparecem como contexto secundário da descrição. Origem, documento e observações permanecem disponíveis na edição do lançamento.

## Compatibilidade

- nenhuma regra financeira foi alterada;
- nenhuma migration nova foi criada;
- schema permanece em 39;
- APIs e tabelas existentes continuam sendo a fonte de verdade.
