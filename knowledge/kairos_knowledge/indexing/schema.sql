CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS meta(key text PRIMARY KEY, value text);          -- embedding_model, embedding_dim
CREATE TABLE IF NOT EXISTS okf_objects(
  path text PRIMARY KEY, okf_file text NOT NULL, type text, title text, privacy text, trust text,
  tags text[], frontmatter jsonb, body text, content_hash text, version int DEFAULT 1, updated_at timestamptz);
CREATE TABLE IF NOT EXISTS chunks(
  chunk_id text PRIMARY KEY, path text REFERENCES okf_objects(path) ON DELETE CASCADE, ord int,
  heading text, text text,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(heading,'') || ' ' || text)) STORED,
  embedding vector(__DIM__));
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS chunks_vec ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS edges(src text, dst text, relation text, weight real DEFAULT 1,
  PRIMARY KEY (src, dst, relation));
CREATE TABLE IF NOT EXISTS memories(
  memory_id text PRIMARY KEY, kind text, scope text, org_id text, owner text, task_id text,
  content text, summary text, derived_from text[], tags text[], importance real, stale bool DEFAULT false,
  created_at timestamptz, last_used_at timestamptz, embedding vector(__DIM__));
CREATE INDEX IF NOT EXISTS memories_derived ON memories USING gin(derived_from);
CREATE TABLE IF NOT EXISTS working_sets(pid int PRIMARY KEY, data jsonb, updated_at timestamptz);
