# DPE v0.10.3 — Cursos e Receitas UX Rebuild

## Objetivo

Reduzir a carga cognitiva da área de Cursos separando três tarefas diferentes: analisar resultado, preencher dados mensais e administrar o cadastro estrutural de cursos/ofertas.

## Nova experiência

### Visão dos cursos

É a entrada padrão. Mostra cada curso consolidado com alunos, receita, custo distribuído, resultado e margem. As ofertas ficam recolhidas e aparecem somente quando o usuário abre o curso.

### Alunos e receitas

Área dedicada apenas à entrada dos dados do mês. A tabela mostra curso/oferta, alunos ativos, pagantes, receita líquida e situação do preenchimento. Ticket, custo por aluno, resultado e margem deixam de competir com os campos de entrada.

### Cursos e ofertas

Cadastro estrutural acessado a partir da própria área Cursos. Cursos são exibidos primeiro; as ofertas ficam em um segundo bloco e podem ser filtradas diretamente pelo curso escolhido. A sidebar deixa de repetir esse destino.

## Formulário econômico

O formulário principal prioriza:
- alunos ativos;
- alunos pagantes;
- receita bruta;
- bolsas e descontos;
- outras deduções;
- indicação de receita realizada ou estimada.

Origem, referência, observações e eventual receita líquida manual ficam em Informações adicionais. O sistema explica o valor líquido calculado antes de salvar.

## Linguagem

Termos visíveis como produto econômico são substituídos por curso. Produto/oferta continuam como conceitos internos do backend para compatibilidade e rastreabilidade.

## Backend e schema

Nenhuma regra financeira foi alterada. O domínio econômico, snapshots, rateio e auditoria permanecem os mesmos. Não há migration nova; schema 39 continua canônico.
