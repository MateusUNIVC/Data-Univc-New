# Data UNIVC UI Foundation — v0.8.22.0

## Objetivo

A v0.8.22.0 inicia uma camada transversal de produto sem reconstruir novamente a DADM V2. A arquitetura aprovada — Visão Geral, Pessoas & Setores, Experiência, Análise Comparativa e Dados & Integração — permanece congelada. A fundação combina a organização e a densidade da DADM V2 com o shell institucional e a consistência já presentes no UI V2.

## Contrato visual compartilhado

`static/css/data-univc-foundation.css` centraliza tokens de cor, superfícies, bordas, sombra, raio e motion, além de componentes compartilhados de campo, senha, status e operação longa. `static/js/data-univc-ui.js` fornece a biblioteca de ícones e o renderer de progresso.

Os módulos continuam livres para ter layouts específicos do domínio. A fundação não obriga DPE, DM ou DADM a terem a mesma tela; ela obriga ações equivalentes a parecerem e se comportarem como partes do mesmo produto.

## Sincronização: contrato de progresso

Há duas modalidades visuais:

1. **Indeterminada** — usada durante preparação ou quando a integração não fornece um total confiável. A interface informa a etapa em andamento e nunca inventa uma porcentagem.
2. **Determinada** — usada somente depois de existir um denominador estável. A porcentagem pode avançar, mas não retrocede durante a execução.

### TALLOS

O endpoint `/v4/reports` é consultado em chunks de até 90 dias. Antes desta release, `total_expected` crescia quando cada chunk era descoberto, o que permitia situações como 71% → 67% mesmo com mais registros processados.

Agora `DADMTallosClient.plan_report_pages()` busca a primeira página de todos os chunks antes do processamento, soma seus totais e fixa `total_expected`. As primeiras páginas são reutilizadas; portanto a preparação não adiciona chamadas duplicadas ao fluxo normal. Enquanto esse planejamento acontece, a DADM V2 mostra **Preparando sincronização** com progresso indeterminado. Depois, a barra usa `records_received / total_expected`.

Se a origem mudar durante a própria execução e forem recebidos mais registros que o snapshot inicial, o histórico final é ajustado para permanecer verdadeiro, sem alterar o denominador enquanto a barra determinada está ativa.

### SEI

As integrações SEI atuais são majoritariamente chamadas HTTP síncronas e não expõem contagem incremental confiável. Por isso DM e shell acadêmico usam o mesmo componente visual em modo indeterminado, com etapa e mensagem específicas. Uma futura evolução pode criar jobs persistidos para SEI e migrar automaticamente para progresso determinado quando os endpoints passarem a expor `current/total`.

## Iconografia

A fundação define um conjunto de SVGs com viewBox 24×24, stroke uniforme e sem dependência de caracteres Unicode. O ícone do SEI representa integração/sincronização, não um documento genérico. UI V2 e DADM V2 passam a usar a mesma linguagem.

## DADM V2

A estrutura aprovada não muda. Nesta fase:

- usuário volta ao rodapé da sidebar;
- sidebar adota os melhores detalhes institucionais do UI V2;
- token TALLOS ganha campo consistente e controle de visibilidade;
- navegação usa biblioteca SVG compartilhada;
- comparação de um único mês usa snapshot horizontal com nome e valor visíveis;
- séries com dois ou mais meses continuam em linha;
- tooltip escolhe o lado com mais espaço para evitar recorte.

## Rollout

A fundação já é carregada por DTNH/DCS, DM, DPE, DADM, DADM V2 e workspace gerencial. A adoção deve continuar de forma incremental: primeiro componentes transversais (progressos, ícones, campos, feedback), depois refinamentos específicos de cada domínio. Não copiar a arquitetura da DADM para diretorias com fluxos diferentes.

## Banco e deploy

Não há alteração de schema. A versão continua em `SCHEMA_VERSION = 29` e a última migration segue sendo `029_dadm_tallos_rating_1_10_v08203.sql`.
