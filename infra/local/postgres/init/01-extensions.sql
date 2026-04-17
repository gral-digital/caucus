-- Estensioni necessarie per il dominio legale italiano.
-- Questo file viene eseguito solo alla PRIMA creazione del volume Postgres.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- trigram fuzzy search su articoli/citazioni
CREATE EXTENSION IF NOT EXISTS "unaccent";      -- rimuove accenti (importante per italiano)
CREATE EXTENSION IF NOT EXISTS "ltree";         -- gerarchie materializzate (libro/titolo/articolo)
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector
CREATE EXTENSION IF NOT EXISTS "btree_gin";     -- combinare gin con btree su jsonb + tsvector

-- Text-search config 'italian' built-in è ok ma beneficia molto da unaccent.
-- Creiamo una config custom 'italian_unaccent' usata da norm_chunk.text_tsv.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'italian_unaccent') THEN
    CREATE TEXT SEARCH CONFIGURATION italian_unaccent (COPY = italian);
    ALTER TEXT SEARCH CONFIGURATION italian_unaccent
      ALTER MAPPING FOR hword, hword_part, word WITH unaccent, italian_stem;
  END IF;
END
$$;
