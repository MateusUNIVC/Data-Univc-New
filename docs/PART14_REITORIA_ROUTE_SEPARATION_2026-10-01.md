# Parte 14 — Reitoria Route Separation

## Objetivo
Separar a administração da Reitoria do painel acadêmico, eliminando a mistura de DOM/CSS e a navegação por hash que causava scroll e inconsistência visual.

## Rotas
- `/reitoria`: administração; abre prioritariamente em **Usuários e acessos**.
- `/reitoria/academico`: indicadores acadêmicos consolidados de DTNH + DCS.
- `/admin/users`: redireciona para `/reitoria`.

## Administração
A página administrativa não carrega `data-univc-academic-charts.js` nem JavaScript acadêmico. Mantém Usuários e acessos, Visão institucional, Auditoria e links para as diretorias.

## Acadêmico
A nova página usa a mesma fundação visual de DTNH/DCS (`app.css`, `data-univc-foundation.css`, `ui-v2.css`) e possui sidebar própria com:
1. NPS da instituição — alunos;
2. NPS dos cursos;
3. NPS da instituição — docentes;
4. Avaliação docente;
5. Aprovação e notas.

Os endpoints e cálculos consolidados da Parte 12 foram preservados. Não há migration de banco. Schema permanece 49.
