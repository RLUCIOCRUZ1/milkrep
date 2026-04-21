-- Adiciona coluna `preposto` em `pedidos` e trata `vw_pedidos` conforme o tipo do objeto.
-- Execute no Supabase SQL Editor.

BEGIN;

ALTER TABLE public.pedidos
ADD COLUMN IF NOT EXISTS preposto text;

DO $$
DECLARE
    v_relkind "char";
BEGIN
    SELECT c.relkind
      INTO v_relkind
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname = 'vw_pedidos'
     LIMIT 1;

    IF v_relkind = 'r' THEN
        -- `vw_pedidos` existe como tabela física.
        EXECUTE 'ALTER TABLE public.vw_pedidos ADD COLUMN IF NOT EXISTS preposto text';
    ELSIF v_relkind = 'v' THEN
        -- `vw_pedidos` é VIEW: não recebe ALTER TABLE ADD COLUMN.
        RAISE NOTICE 'vw_pedidos é VIEW. Recrie com CREATE OR REPLACE VIEW incluindo a coluna preposto.';
    ELSIF v_relkind = 'm' THEN
        -- `vw_pedidos` é materialized view.
        RAISE NOTICE 'vw_pedidos é MATERIALIZED VIEW. Recrie incluindo preposto e faça REFRESH MATERIALIZED VIEW.';
    ELSE
        RAISE NOTICE 'Objeto public.vw_pedidos não encontrado.';
    END IF;
END $$;

COMMIT;

-- Opcional: inspecionar definição atual da view para recriar com `preposto`.
-- SELECT pg_get_viewdef('public.vw_pedidos'::regclass, true);
