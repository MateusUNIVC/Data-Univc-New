# DPE v0.9.6.21 — padronização do frontend e demonstração local

## Objetivo

Permitir homologar a DPE V2 sem Supabase nem dados reais, mantendo o mesmo padrão visual das demais diretorias.

## Início rápido no Windows

Execute `TESTAR_DPE_DEMO.bat`. O launcher mostra cinco etapas na tela. Na primeira execução ele instala dependências apenas se estiverem faltando; nas próximas execuções essa etapa é pulada. O servidor abre em uma segunda janela e o navegador só é aberto depois que o health-check responde em `http://127.0.0.1:8000/api/health/live`. O banco utilizado é `univc_dpe_demo.db`.

O banco é persistente entre execuções para que alterações manuais possam ser testadas. Para restaurar o conjunto original, encerre o servidor e execute `RESETAR_DPE_DEMO.bat`.

## Dados fictícios

A competência 2026-09 contém os produtos Administração, Direito, ADS, Ciências Contábeis, Engenharia Mecânica, Engenharia de Produção, Arquitetura e Urbanismo, Comunicação Social, Agronomia, Odontologia, Fisioterapia, Enfermagem, Psicologia, Educação Física, Farmácia e Medicina Veterinária.

Alguns produtos possuem mais de uma oferta para exercitar modalidade e turno. A base também contém professores compartilhados, uma atividade compartilhada entre Direito Matutino e Noturno, folha, despesas administrativas e de infraestrutura, custos diretos de laboratório, alunos, receitas e um lote fictício em staging.

Nenhum valor representa dado real do UNIVC.

## Segurança

O seed recusa qualquer `DATABASE_URL` que não seja SQLite. O atalho usa `ENVIRONMENT=local` e `AUTH_DISABLED=true`. O backend recusa `AUTH_DISABLED=true` caso `ENVIRONMENT` seja `prod` ou `production`.

## Banco e schema

Não há migration nova. A aplicação permanece no schema 39. O SQLite local é criado pelas models SQLAlchemy e recebe o ledger de schema esperado apenas para homologação.


## Hotfix 0.9.6.21.1

O launcher original da 0.9.6.21 usava `pip install -q` em toda execução e abria o navegador antes do Uvicorn estar pronto. O hotfix remove o modo silencioso, instala somente quando necessário, limita espera de rede e aguarda o health-check antes de abrir a DPE.


## Hotfix 0.9.6.21.2 — Python 3.13t / Windows

Em Windows com CPython 3.13 free-threaded (`cp313t`), algumas dependências da pilha local não oferecem wheel adequada para o conjunto usado pela demonstração. O launcher não tenta mais compilar extensões nativas. Ele rejeita ambientes free-threaded, procura CPython convencional 3.12/3.13/3.11, remove apenas a `.venv` incompatível e pode oferecer instalação de Python 3.12 via `winget`. A instalação local usa somente wheels binárias (`--only-binary=:all:`).
