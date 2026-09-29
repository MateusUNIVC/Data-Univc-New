# DPE v0.10.2 — Docentes UX Rebuild

## Objetivo

Reduzir a carga cognitiva da area Docentes sem alterar o dominio de dados ou as regras historicas ja implementadas. A interface deixa de mostrar simultaneamente cadastro de professores, cadastro de disciplinas, atividades mensais e conciliacao da folha.

## Nova estrutura

A area Docentes possui quatro visoes internas:

1. **Aulas e carga** — trabalho mensal: professor, disciplina, turma, curso/oferta, carga e vigencia.
2. **Folha docente** — conferencia dos lancamentos de folha e seus professores.
3. **Professores** — cadastro permanente da pessoa.
4. **Disciplinas** — cadastro permanente da materia.

Somente uma visao fica exposta por vez. O mes continua sendo controlado pelo seletor global da DPE.

## Principios de UX

- cadastro permanente nao compete visualmente com o trabalho mensal;
- nomes tecnicos como alias sao traduzidos para linguagem de negocio, como **nomes reconhecidos na folha**;
- sugestoes de professor na folha continuam exigindo confirmacao humana;
- campos tecnicos de integracao, origem e observacoes ficam em divulgacao progressiva;
- a associacao professor-disciplina-curso continua sendo mensal e historica;
- dois professores podem lecionar a mesma disciplina/turma no mesmo mes, simultaneamente ou em periodos diferentes.

## Banco e backend

Nenhuma tabela, API financeira ou regra de calculo foi alterada. O schema permanece em **39**.
