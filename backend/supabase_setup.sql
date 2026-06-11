-- ============================================================
-- Supabase Setup for Python Q&A Assistant
-- Run these in the Supabase SQL Editor
-- IMPORTANT: Embedding dim = 384 (all-MiniLM-L6-v2, NOT OpenAI 1536)
-- ============================================================

-- 1. Enable pgvector extension
create extension if not exists vector;

-- 2. Documents table
create table if not exists documents (
  id bigserial primary key,
  row_number integer unique not null,       -- original index in question_answer.json
  content text not null,                    -- full "Question: ... Answer: ..." text
  embedding vector(384),                    -- all-MiniLM-L6-v2 produces 384-dim
  created_at timestamp default now()
);

-- 3. HNSW index for fast approximate nearest-neighbor search
create index if not exists documents_embedding_idx
  on documents using hnsw (embedding vector_cosine_ops);

-- 4. RPC function used by retriever.py
create or replace function match_documents(
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id bigint,
  row_number integer,
  content text,
  similarity float
)
language sql stable
as $$
  select
    id,
    row_number,
    content,
    1 - (embedding <=> query_embedding) as similarity
  from documents
  where 1 - (embedding <=> query_embedding) > match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;
