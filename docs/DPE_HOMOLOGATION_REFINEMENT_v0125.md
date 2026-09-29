# DPE v0.12.5 — Homologação e Refinamento

## Objetivo

A v0.12.5 encerra a sequência v0.12.x sem introduzir um novo domínio financeiro. O objetivo desta release é transformar a fundação funcional das versões v0.12.0–v0.12.4 em uma experiência mais consistente, responsiva, compreensível e acessível para o usuário administrativo.

A regra desta fase foi simples: **não criar uma nova funcionalidade financeira apenas para justificar a versão**. O trabalho foi concentrado em homologação, consistência visual, estados da interface, acessibilidade e segurança de interação.

## O que foi refinado

### 1. Navegação e acessibilidade estrutural

- link “Pular para o conteúdo principal” para navegação por teclado;
- `main` focável como destino do skip link;
- seção ativa expõe `aria-current="page"` na navegação;
- páginas internas atualizam `aria-hidden` conforme a navegação;
- abas com `role="tab"` ganharam navegação por ArrowLeft, ArrowRight, Home e End;
- foco visível foi reforçado em botões, navegação e ações interativas.

### 2. Modais

Foi consolidado um gerenciador comum para os modais DPE.

Ao abrir um modal:

- o elemento que iniciou a ação é lembrado;
- o foco entra no modal;
- o restante da página deixa de receber scroll;
- `aria-hidden` é atualizado.

Durante a interação:

- Tab e Shift+Tab permanecem dentro do modal;
- Esc fecha a janela quando apropriado.

Ao fechar:

- o foco retorna ao elemento que abriu a janela.

Isso foi aplicado aos fluxos de competência, importação, gestão, financeiro, Cost Engine e ao novo diálogo de confirmação.

### 3. Confirmações críticas

Os diálogos nativos de navegador `confirm()` e `prompt()` foram removidos da trilha JavaScript da DPE.

Ações como:

- estornar despesa;
- estornar atividade docente;
- desvincular folha;
- oficializar distribuição;
- atualizar snapshot de cursos;
- excluir registros legados;
- criar dados demonstrativos;

passam por um diálogo institucional único.

O diálogo pode:

- explicar a consequência da operação;
- usar tratamento visual de atenção/perigo;
- exigir justificativa quando a regra de negócio necessita dela;
- anunciar erros de preenchimento;
- devolver o foco ao acionador após cancelamento/conclusão.

### 4. Carregamento e feedback

O carregamento global passou a ser ref-counted para lidar corretamente com operações simultâneas.

Durante uma atualização:

- a região principal recebe `aria-busy="true"`;
- é exibido um status textual “Atualizando dados…”;
- a área de status do sistema informa “Atualizando…”;
- ao encerrar todas as operações, o estado volta a “Sincronizado”.

Alertas de sucesso, informação, atenção e erro foram padronizados com:

- título;
- ícone;
- mensagem;
- botão de fechamento;
- `aria-live`/`role` adequados;
- foco automático em erros importantes.

### 5. Erros de formulário

Erros de formulário passam a utilizar um helper comum que:

- exibe a mensagem de forma consistente;
- remove o estado oculto;
- torna a mensagem focável;
- move o foco para o erro quando necessário.

O objetivo é impedir que um erro apareça visualmente em outra parte do modal sem que o usuário perceba o que bloqueou o salvamento.

### 6. Estados vazios

Tabelas e painéis importantes deixaram de apresentar apenas textos soltos como “Nenhum registro”.

Foi criado um padrão reutilizável de empty state com:

- ícone discreto;
- título curto;
- explicação contextual;
- espaço visual suficiente para diferenciar “sem dados” de erro de carregamento.

O padrão foi aplicado em Despesas, Cursos/Economics, Docentes, Distribuição, Fechamento e Analytics.

### 7. Combobox docente

O combobox utilizado na operação docente foi refinado para uso por teclado e tecnologias assistivas:

- `aria-controls`;
- `aria-haspopup="listbox"`;
- opções com identificação própria;
- `aria-selected`;
- `aria-activedescendant` durante navegação;
- ArrowDown/ArrowUp;
- Enter;
- Esc.

### 8. Tooltips de conceitos gerenciais

Conceitos que podem gerar dúvida administrativa receberam ajuda contextual sem poluir a interface.

Na Visão Geral, foram adicionadas explicações para:

- Margem operacional;
- Custo por aluno × Ticket;
- Composição do custo por curso.

Os tooltips funcionam por hover e por foco de teclado.

### 9. Responsividade e legibilidade

A folha DPE foi refinada para:

- controles com altura consistente;
- tipografia ligeiramente maior nos elementos densos;
- espaçamento mais previsível em formulários e painéis;
- melhor leitura das tabelas;
- hover/focus de linhas sem alterar o significado dos dados;
- modais mais confortáveis em telas estreitas;
- reorganização de blocos em 980 px, 720 px e 520 px;
- primeira coluna fixa nas grades financeiras mais densas em telas pequenas, preservando a identificação do curso/despesa durante scroll horizontal.

A preferência `prefers-reduced-motion` já existente foi preservada.

## O que não mudou

A v0.12.5 não altera:

- fórmulas financeiras;
- Allocation Engine;
- policies;
- economics;
- fechamento e governança;
- estrutura de cursos;
- autenticação;
- permissões;
- módulos DTNH, DCS, DADM, DM ou Avaliação Docente.

Também não foi criada nova tabela nem nova migration.

## Banco

- versão esperada do schema: **42**;
- migration nova nesta release: **nenhuma**;
- última migration obrigatória: `database/042_dpe_productivity_v0123.sql`;
- migration anterior: `database/041_dpe_allocation_policies_v0121.sql`.

Uma instalação já atualizada para v0.12.4/schema 42 pode seguir para v0.12.5 sem alteração no banco.

## Testes adicionados

A v0.12.5 acrescenta testes estáticos/regressivos para:

1. skip link, landmark principal e status de carregamento acessível;
2. estado ARIA dos modais e descrição do diálogo crítico;
3. ausência de `confirm()`/`prompt()` nativos nos JavaScripts DPE;
4. gerenciamento comum de modal, foco, teclado e `aria-busy`;
5. contrato de acessibilidade do combobox e das abas;
6. estilos de foco, empty state, tooltip, confirmação, responsividade e reduced motion;
7. metadados da release e preservação do schema 42.

Suíte acumulada: **80 testes aprovados**.

## Critério de homologação recomendado

Antes de promover a release para produção, testar pelo menos uma competência de homologação percorrendo:

`Receitas -> Despesas -> Docentes -> Distribuição -> Cursos/Analytics -> Fechamento`

E, além da correção dos valores, verificar:

- navegação por teclado;
- abrir/fechar modais;
- uma confirmação crítica;
- um erro de formulário;
- uma tela sem dados;
- uma tela estreita/mobile;
- feedback de carregamento e sucesso.

## Limitação da validação automatizada visual

O ambiente de desenvolvimento desta sequência bloqueou anteriormente o acesso do Chromium automatizado ao servidor local (`ERR_BLOCKED_BY_ADMINISTRATOR`). Por isso, a release utiliza regressão funcional, testes estruturais de HTML/ARIA, validação de sintaxe, seed e verificação de artefatos, mas a inspeção visual final em navegador real continua sendo uma etapa de homologação recomendada antes da promoção para produção.
