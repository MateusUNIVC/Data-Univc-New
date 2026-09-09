# DADM TALLOS — Reconciliação das avaliações v0.8.20.3

## Evidência usada na homologação

A exportação oficial TALLOS fornecida para a revisão contém **536 linhas de atendimento**. A coluna `Avaliação` contém:

- **504** ocorrências de `S/A`;
- **32** avaliações numéricas;
- **0** avaliações com nota 0.

Distribuição das 32 avaliações numéricas:

| Nota | Quantidade |
|---:|---:|
| 1 | 0 |
| 2 | 0 |
| 3 | 2 |
| 4 | 0 |
| 5 | 0 |
| 6 | 0 |
| 7 | 1 |
| 8 | 1 |
| 9 | 4 |
| 10 | 24 |

A média desse recorte é **9,28125 / 10**. A menor nota observada é 3 e a maior é 10. Isso não prova que 1 e 2 sejam impossíveis; apenas confirma que a escala válida deve aceitar **1 a 10** e que, neste recorte, não existe evidência para tratar `0` como avaliação real.

## Contrato implementado

- `level` entre 1 e 10 → avaliação válida;
- `level = 0` → ausência de avaliação na homologação atual;
- `S/A`, `NULL`, campo ausente ou valor não numérico → ausência;
- ausência não participa de média, distribuição nem comparação;
- média por operador é calculada por **mês**, usando somente avaliações válidas daquele operador naquele mês;
- mês sem avaliações → `rating_avg = NULL` e interface `—`;
- um protocolo pode conter múltiplas sessões; a nota permanece vinculada à sessão/`source_id`, não é propagada por protocolo.

## Regra de validação

O banco normalizado e os agregados aplicam a faixa 1–10 de forma defensiva. A página de auditoria permite comparar `level` bruto e `rating` normalizado sem expor PII de clientes.
