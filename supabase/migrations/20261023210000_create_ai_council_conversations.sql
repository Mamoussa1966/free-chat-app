-- Supabase PostgreSQL storage for canonical AI Council conversations.
-- Apply only to a dedicated Supabase project after reviewing the free-tier
-- limits. The adapter uses the user's Auth JWT; never use service_role here.

create table public.ai_council_conversations (
    conversation_id text primary key,
    owner_id uuid not null references auth.users (id) on delete cascade,
    canonical_record jsonb not null,
    snapshot_sha256 text not null,
    created_at timestamptz not null default pg_catalog.now(),
    updated_at timestamptz not null default pg_catalog.now(),

    constraint ai_council_conversations_id_nonempty
        check (pg_catalog.length(pg_catalog.btrim(conversation_id)) between 1 and 1024),
    constraint ai_council_conversations_checksum_format
        check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    constraint ai_council_conversations_record_object
        check (pg_catalog.jsonb_typeof(canonical_record) = 'object'),
    constraint ai_council_conversations_record_id_match
        check (canonical_record ->> 'conversation_id' = conversation_id),
    constraint ai_council_conversations_canonical_contract
        check (canonical_record ->> 'canonical_store_contract' = 'V26_3_CANONICAL_CONVERSATION_STORE'),
    constraint ai_council_conversations_messages_array
        check (pg_catalog.jsonb_typeof(canonical_record -> 'messages') = 'array'),
    constraint ai_council_conversations_requests_array
        check (pg_catalog.jsonb_typeof(canonical_record -> 'requests') = 'array'),
    constraint ai_council_conversations_rounds_array
        check (pg_catalog.jsonb_typeof(canonical_record -> 'rounds') = 'array')
);

create index ai_council_conversations_owner_updated_idx
    on public.ai_council_conversations (owner_id, updated_at desc);

alter table public.ai_council_conversations enable row level security;
alter table public.ai_council_conversations force row level security;

revoke all on table public.ai_council_conversations from anon, authenticated;
grant select, insert, update, delete on table public.ai_council_conversations to authenticated;

create policy ai_council_conversations_select_own
    on public.ai_council_conversations
    for select
    to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()));

create policy ai_council_conversations_insert_own
    on public.ai_council_conversations
    for insert
    to authenticated
    with check (auth.uid() is not null and owner_id = (select auth.uid()));

create policy ai_council_conversations_update_own
    on public.ai_council_conversations
    for update
    to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()))
    with check (auth.uid() is not null and owner_id = (select auth.uid()));

create policy ai_council_conversations_delete_own
    on public.ai_council_conversations
    for delete
    to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()));

comment on table public.ai_council_conversations is
    'Canonical AI Council conversation snapshots. Access is restricted by Supabase Auth + Postgres RLS.';
