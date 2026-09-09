# DADM TALLOS Identifier Alignment — v0.9.6.5

## Problema

A TALLOS persiste `to_department` como um identificador completo, por exemplo `financeiro_12c84`. A v0.9.6.4 havia configurado o escopo de leitura de `dadm@ivc.br` apenas com o sufixo curto (`12c84`). Como as consultas usam igualdade no backend/SQL, registros reais podiam ser excluídos do escopo autorizado.

## Identificadores canônicos

- `financeiro_12c84` — Financeiro
- `secretaria_academica_a967b` — Secretaria Acadêmica
- `mestrado_8155e` — Mestrado
- `negociacao_b623` — Negociação
- `prouni_nbolsa_fies_9bc56` — Prouni / Nbolsa / Fies
- `estagio_80bc4` — Estágio

Os sufixos curtos permanecem como aliases para compatibilidade com fixtures e bases locais antigas. A API `/api/auth/me` publica apenas as chaves canônicas.

## Nomes de exibição

A normalização TALLOS passa a remover sufixos hexadecimais de 5 ou mais caracteres do nome automático. Assim, a chave técnica `financeiro_12c84` continua preservada, mas o nome automático vira `Financeiro`. Para os seis departamentos governados pelo escopo limitado, os nomes institucionais configurados prevalecem, incluindo acentuação.

Mapeamentos editados manualmente (`updated_by` preenchido) nunca são substituídos pelo reparo automático.

## Compatibilidade

- ingestão continua global para ambos os usuários DADM EDIT;
- leitura de `dadm@ivc.br` continua limitada aos seis departamentos;
- Rodrigo/Reitoria continuam com leitura integral;
- nenhum dado precisa ser apagado;
- nenhum schema/migration novo.
