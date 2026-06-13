-- ============================================================
-- Supabase Setup for Python Q&A Assistant
-- Run ALL sections in the Supabase SQL Editor
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- SECTION 1 — Vector store (legacy, kept for reference)
-- NOTE: Retrieval now uses Pinecone. These tables are no longer
--       queried by the backend, but can be kept as a backup.
-- ──────────────────────────────────────────────────────────────

-- Enable pgvector extension (still needed if you kept old data)
create extension if not exists vector;

-- Documents table (was used by old pgvector retriever)
create table if not exists documents (
  id bigserial primary key,
  row_number integer unique not null,
  content text not null,
  embedding vector(384),
  created_at timestamp default now()
);

create index if not exists documents_embedding_idx
  on documents using hnsw (embedding vector_cosine_ops);

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


-- ──────────────────────────────────────────────────────────────
-- SECTION 2 — Chat history (NEW — required for chat features)
-- ──────────────────────────────────────────────────────────────

-- Chat sessions table
create table if not exists chat_sessions (
  id          uuid primary key default gen_random_uuid(),
  title       text not null default 'New Chat',
  summary     text,                          -- AI-generated conversation summary
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Index for fast "most recent" queries
create index if not exists chat_sessions_updated_idx
  on chat_sessions (updated_at desc);

-- Chat messages table
create table if not exists chat_messages (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references chat_sessions(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  sources     jsonb not null default '[]',   -- retrieved source docs snapshot
  grounded    boolean not null default false,
  created_at  timestamptz not null default now()
);

-- Index for fast message loading by session
create index if not exists chat_messages_session_idx
  on chat_messages (session_id, created_at asc);

-- ──────────────────────────────────────────────────────────────
-- SECTION 3 — Optional: disable Row Level Security for service key
-- (If you use the SERVICE_ROLE key in the backend, RLS is bypassed
--  automatically. Only run the below if you hit permission errors.)
-- ──────────────────────────────────────────────────────────────
-- alter table chat_sessions disable row level security;
-- alter table chat_messages  disable row level security;


-- ──────────────────────────────────────────────────────────────
-- SECTION 4 — User-based sessions (run after Section 2)
-- Adds user_id + Row Level Security so each user only sees their own data.
-- ──────────────────────────────────────────────────────────────

-- 4a. Add user_id column to chat_sessions (nullable for backwards-compat)
alter table chat_sessions
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

-- 4b. Add user_id to chat_messages (denormalised for fast RLS checks)
alter table chat_messages
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

-- 4c. Indexes
create index if not exists chat_sessions_user_idx
  on chat_sessions (user_id, updated_at desc);

create index if not exists chat_messages_user_idx
  on chat_messages (user_id, session_id, created_at asc);

-- 4d. Enable RLS
alter table chat_sessions enable row level security;
alter table chat_messages  enable row level security;

-- 4e. RLS policies for chat_sessions
-- Users can only see / mutate their own sessions
-- (DROP IF EXISTS makes this block safe to re-run)
drop policy if exists "sessions: select own" on chat_sessions;
drop policy if exists "sessions: insert own" on chat_sessions;
drop policy if exists "sessions: update own" on chat_sessions;
drop policy if exists "sessions: delete own" on chat_sessions;

create policy "sessions: select own"   on chat_sessions for select using (auth.uid() = user_id);
create policy "sessions: insert own"   on chat_sessions for insert with check (auth.uid() = user_id);
create policy "sessions: update own"   on chat_sessions for update using (auth.uid() = user_id);
create policy "sessions: delete own"   on chat_sessions for delete using (auth.uid() = user_id);

-- 4f. RLS policies for chat_messages
drop policy if exists "messages: select own" on chat_messages;
drop policy if exists "messages: insert own" on chat_messages;
drop policy if exists "messages: update own" on chat_messages;
drop policy if exists "messages: delete own" on chat_messages;

create policy "messages: select own"   on chat_messages for select using (auth.uid() = user_id);
create policy "messages: insert own"   on chat_messages for insert with check (auth.uid() = user_id);
create policy "messages: update own"   on chat_messages for update using (auth.uid() = user_id);
create policy "messages: delete own"   on chat_messages for delete using (auth.uid() = user_id);

-- NOTE: The backend uses the user's JWT (anon key + Bearer token) so RLS is
-- automatically enforced. The SERVICE_ROLE key bypasses RLS for admin tasks only.
