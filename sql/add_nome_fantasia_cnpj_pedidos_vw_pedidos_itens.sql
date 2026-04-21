BEGIN;

ALTER TABLE public.pedidos
ADD COLUMN IF NOT EXISTS nome_fantasia text;

ALTER TABLE public.pedidos
ADD COLUMN IF NOT EXISTS cnpj text;

-- Recria a view com os novos campos da tabela `pedidos`.
DROP VIEW IF EXISTS public.vw_pedidos_itens;

CREATE VIEW public.vw_pedidos_itens AS
SELECT
  p.id AS pedido_pk,
  p.customer,
  p.store,
  p.nome_fantasia,
  p.cnpj,
  p.customer_name,
  p.order_no,
  p.style,
  p.rsn,
  p.status_pedido,
  p.descricao_modelo,
  p.genero,
  p.cod_desconto,
  p.total,
  p.cfop,
  p.status_customer,
  p.campanha,
  p.confirmado,
  p.preco_bruto,
  p.preco_liquido,
  p.pick_date,
  p.data_original,
  p.data_faturamento,
  p.preposto,
  i.id AS item_pk,
  i.sku,
  i.tamanho,
  i.quantidade,
  i.rsn AS item_rsn,
  i.style AS item_style
FROM public.pedidos p
LEFT JOIN public.itens_pedido i
  ON p.order_no::text = i.pedido_id::text
 AND (
      (NULLIF(TRIM(i.rsn::text), '') IS NULL AND NULLIF(TRIM(i.style::text), '') IS NULL)
      OR
      (
        COALESCE(NULLIF(TRIM(p.rsn::text), ''), '#') = COALESCE(NULLIF(TRIM(i.rsn::text), ''), '#')
        AND COALESCE(NULLIF(TRIM(p.style::text), ''), '#') = COALESCE(NULLIF(TRIM(i.style::text), ''), '#')
      )
 );

COMMIT;

NOTIFY pgrst, 'reload schema';
