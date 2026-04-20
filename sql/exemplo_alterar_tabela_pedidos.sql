-- Exemplo: alinhar nomes de colunas da tabela public.pedidos ao slug da planilha
-- (PostgreSQL / Supabase). Ajuste nomes antigos/novos conforme a saída de:
--   python scripts/listar_cabecalhos_planilha.py
--
-- ONDE EXECUTAR: Supabase → SQL Editor → New query → colar → Run
--
-- ATENÇÃO:
-- 1) Faça backup ou export dos dados se já houver produção.
-- 2) Quem referencia a coluna antiga (views, funções, RLS, API) precisa ser atualizado.
-- 3) Renomear coluna NÃO migra dados; só o identificador muda.

-- Exemplo de renomear colunas “canônicas do app” para bater com o slug da planilha:
-- ALTER TABLE public.pedidos RENAME COLUMN codigo_loja TO store;
-- ALTER TABLE public.pedidos RENAME COLUMN razao_social TO customer_name;
-- ALTER TABLE public.pedidos RENAME COLUMN modelo TO style;

-- Exemplo de criar coluna nova (se a planilha tiver campo que ainda não existe no banco):
-- ALTER TABLE public.pedidos ADD COLUMN IF NOT EXISTS desconto_em_percentual numeric;

-- Tipos comuns: text, numeric, bigint, boolean, timestamptz

-- Se precisar remover coluna legada (cuidado: perda de dados):
-- ALTER TABLE public.pedidos DROP COLUMN IF EXISTS nome_coluna_antiga;
