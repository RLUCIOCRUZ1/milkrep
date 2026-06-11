-- Colunas % (coluna) e provisao contabil (previsao) na comissao_complete.
-- Execute no SQL Editor do Supabase se ainda não existirem.

BEGIN;

ALTER TABLE public.comissao_complete
ADD COLUMN IF NOT EXISTS coluna text;

ALTER TABLE public.comissao_complete
ADD COLUMN IF NOT EXISTS previsao text;

COMMIT;

NOTIFY pgrst, 'reload schema';
