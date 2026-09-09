# v0.8.28.2 — Academic Visual Polish

Patch visual de DTNH/DCS sem alteração de contrato de dados.

## Sidebar

Todos os títulos de grupos acadêmicos usam a mesma cor `#a9d6bf`, já aplicada ao grupo NPS Docente. Isso inclui NPS Discente, NPS Docente, Indicadores acadêmicos, Gestão e Sistema.

## Composição do NPS docente

O gráfico continua apresentando as mesmas porcentagens, mas passa a diferenciar semanticamente as categorias:

- Promotores: verde `#0e8058`;
- Neutros: âmbar `#c08214`;
- Detratores: vermelho `#b64a4a`.

A paleta é aplicada por `compositionTone`, separada de `status`, para não confundir composição NPS com status de meta.

## Compatibilidade

- sem migration;
- schema 31;
- nenhum cálculo NPS alterado.
