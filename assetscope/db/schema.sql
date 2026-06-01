-- AssetScope retrieval schema: PostgreSQL + pgvector.
-- Applied automatically on first VectorStore connection (idempotent) and by the
-- pgvector image's init step. Embedding dim defaults to 384 (all-MiniLM-L6-v2).

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per ingested source document (a trial, abstract, mechanism record...).
CREATE TABLE IF NOT EXISTS documents (
    id           BIGSERIAL PRIMARY KEY,
    source_type  TEXT NOT NULL,                 -- clinical_trials | pubmed | chembl | open_targets | internal
    source_id    TEXT NOT NULL,                 -- NCT id, PMID, ChEMBL id, ...
    citation_id  TEXT NOT NULL,                 -- stable handle the agent cites
    title        TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL DEFAULT '',
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_type, source_id)
);

-- Chunked, embedded content. `content` is searched two ways: by vector cosine
-- similarity (embedding) and by keyword (tsv full-text), then fused by RRF.
CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL DEFAULT 0,
    content      TEXT NOT NULL,
    embedding    vector(384),
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    UNIQUE (document_id, chunk_index)
);

-- Approximate-NN index for vector search (cosine). HNSW gives good recall/latency.
-- m = graph degree; ef_construction = build-time candidate list (recall vs build cost).
-- vector_cosine_ops pairs with the <=> cosine-distance operator. Tune recall at query
-- time with: SET LOCAL hnsw.ef_search = 100;
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Keyword / BM25-style search.
CREATE INDEX IF NOT EXISTS chunks_tsv_gin
    ON chunks USING gin (tsv);

CREATE INDEX IF NOT EXISTS chunks_document_id ON chunks (document_id);

-- Saved competitive landscapes (history library; basis for diff/watchlists).
-- Also created on first use by assetscope/storage.py (CREATE TABLE IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS landscapes (
    id             TEXT PRIMARY KEY,
    query          TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    backend        TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    tool_calls     INT NOT NULL DEFAULT 0,
    n_assets       INT NOT NULL DEFAULT 0,
    dropped_claims INT NOT NULL DEFAULT 0,
    landscape      JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS landscapes_created_at ON landscapes (created_at DESC);
