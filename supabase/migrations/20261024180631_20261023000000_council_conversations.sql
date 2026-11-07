-- AI Council Supabase conversation storage, v1.
-- Apply only to a dedicated Supabase project after reviewing the plan.
-- The adapter sends a publishable key + the signed-in user's JWT; no service key is needed.
begin;

create table if not exists public.council_conversations (
    conversation_id text primary key,
    owner_id uuid not null references auth.users(id) on delete cascade,
    schema text not null default 'ai-council-supabase-conversation/v1'
        check (schema = 'ai-council-supabase-conversation/v1'),
    canonical_record jsonb not null,
    checksum text not null check (checksum ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists council_conversations_owner_updated_idx
    on public.council_conversations (owner_id, updated_at desc);

alter table public.council_conversations enable row level security;
alter table public.council_conversations force row level security;

-- Grants and RLS are separate controls. Signed-out visitors get no table privileges.
revoke all on table public.council_conversations from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.council_conversations to authenticated;

drop policy if exists council_conversations_select_own on public.council_conversations;
create policy council_conversations_select_own
    on public.council_conversations for select to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()));

drop policy if exists council_conversations_insert_own on public.council_conversations;
create policy council_conversations_insert_own
    on public.council_conversations for insert to authenticated
    with check (auth.uid() is not null and owner_id = (select auth.uid()));

drop policy if exists council_conversations_update_own on public.council_conversations;
create policy council_conversations_update_own
    on public.council_conversations for update to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()))
    with check (auth.uid() is not null and owner_id = (select auth.uid()));

drop policy if exists council_conversations_delete_own on public.council_conversations;
create policy council_conversations_delete_own
    on public.council_conversations for delete to authenticated
    using (auth.uid() is not null and owner_id = (select auth.uid()));

create or replace function public.guard_council_conversation_row()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_spec record;
    v_row jsonb;
    v_old_row jsonb;
    v_new_row jsonb;
    v_linked jsonb;
    v_id text;
    v_request_id text;
    v_message_id text;
    v_field text;
    v_invalid_count bigint;
    v_row_count bigint;
    v_unique_count bigint;
begin
    if auth.uid() is null or new.owner_id is distinct from auth.uid() then
        raise exception 'conversation owner does not match the authenticated user'
            using errcode = '42501';
    end if;

    if new.conversation_id is null or length(btrim(new.conversation_id)) = 0 then
        raise exception 'conversation_id must not be empty' using errcode = '22023';
    end if;
    if jsonb_typeof(new.canonical_record) is distinct from 'object'
       or new.canonical_record ->> 'conversation_id' is distinct from new.conversation_id
       or new.canonical_record ->> 'canonical_store_contract' is distinct from 'V26_3_CANONICAL_CONVERSATION_STORE' then
        raise exception 'canonical snapshot contract or conversation ID is invalid'
            using errcode = '22023';
    end if;

    if jsonb_typeof(new.canonical_record -> 'messages') is distinct from 'array'
       or jsonb_typeof(new.canonical_record -> 'requests') is distinct from 'array'
       or jsonb_typeof(new.canonical_record -> 'rounds') is distinct from 'array' then
        raise exception 'canonical Message/Request/Round collections must be arrays'
            using errcode = '22023';
    end if;

    -- Required identity IDs must be present and unique within their collection.
    for v_spec in
        select * from (values
            ('messages', 'message_id'),
            ('requests', 'request_id'),
            ('rounds', 'round_id')
        ) as required_ids(collection_name, id_field)
    loop
        select count(*) into v_invalid_count
        from jsonb_array_elements(new.canonical_record -> v_spec.collection_name) as items(value)
        where jsonb_typeof(items.value) is distinct from 'object'
           or nullif(btrim(items.value ->> v_spec.id_field), '') is null;
        if v_invalid_count <> 0 then
            raise exception 'canonical % contains a malformed identity row', v_spec.collection_name
                using errcode = '22023';
        end if;

        select count(*), count(distinct items.value ->> v_spec.id_field)
          into v_row_count, v_unique_count
        from jsonb_array_elements(new.canonical_record -> v_spec.collection_name) as items(value);
        if v_row_count <> v_unique_count then
            raise exception 'canonical % contains duplicate identity IDs', v_spec.collection_name
                using errcode = '22023';
        end if;

        for v_row in
            select items.value
            from jsonb_array_elements(new.canonical_record -> v_spec.collection_name) as items(value)
        loop
            if v_row ? 'conversation_id'
               and (v_row ->> 'conversation_id') is distinct from new.conversation_id then
                raise exception 'canonical row belongs to another conversation'
                    using errcode = '22023';
            end if;
        end loop;
    end loop;

    -- Enforce the present Message -> Request, Request -> Message, and Round -> Request/Message edges.
    for v_row in select items.value from jsonb_array_elements(new.canonical_record -> 'messages') as items(value)
    loop
        v_request_id := nullif(btrim(v_row ->> 'request_id'), '');
        if lower(coalesce(v_row ->> 'role', '')) = 'user' and v_request_id is null then
            raise exception 'canonical user message is missing its request binding' using errcode = '22023';
        end if;
        if v_request_id is not null then
            select items.value into v_linked
            from jsonb_array_elements(new.canonical_record -> 'requests') as items(value)
            where items.value ->> 'request_id' = v_request_id
            limit 1;
            if not found then
                raise exception 'canonical message references a missing request' using errcode = '22023';
            end if;
            if lower(coalesce(v_row ->> 'role', '')) = 'user'
               and (v_linked ->> 'message_id') is distinct from (v_row ->> 'message_id') then
                raise exception 'canonical user message/request binding mismatch' using errcode = '22023';
            end if;
        end if;
    end loop;

    for v_row in select items.value from jsonb_array_elements(new.canonical_record -> 'requests') as items(value)
    loop
        v_message_id := nullif(btrim(v_row ->> 'message_id'), '');
        if v_message_id is null then
            raise exception 'canonical request is missing its message binding' using errcode = '22023';
        end if;
        select items.value into v_linked
        from jsonb_array_elements(new.canonical_record -> 'messages') as items(value)
        where items.value ->> 'message_id' = v_message_id
        limit 1;
        if not found then
            raise exception 'canonical request references a missing message' using errcode = '22023';
        end if;
        if lower(coalesce(v_linked ->> 'role', '')) = 'user'
           and (v_linked ->> 'request_id') is distinct from (v_row ->> 'request_id') then
            raise exception 'canonical request/message binding mismatch' using errcode = '22023';
        end if;
    end loop;

    for v_row in select items.value from jsonb_array_elements(new.canonical_record -> 'rounds') as items(value)
    loop
        v_request_id := nullif(btrim(v_row ->> 'request_id'), '');
        v_message_id := nullif(btrim(v_row ->> 'message_id'), '');
        if v_request_id is null or v_message_id is null then
            raise exception 'canonical round is missing its request or message binding' using errcode = '22023';
        end if;
        select items.value into v_linked
        from jsonb_array_elements(new.canonical_record -> 'requests') as items(value)
        where items.value ->> 'request_id' = v_request_id
        limit 1;
        if not found then
            raise exception 'canonical round references a missing request' using errcode = '22023';
        end if;
        if (v_linked ->> 'message_id') is distinct from v_message_id then
            raise exception 'canonical round/request message binding mismatch' using errcode = '22023';
        end if;
        select items.value into v_linked
        from jsonb_array_elements(new.canonical_record -> 'messages') as items(value)
        where items.value ->> 'message_id' = v_message_id
        limit 1;
        if not found then
            raise exception 'canonical round references a missing message' using errcode = '22023';
        end if;
    end loop;

    if tg_op = 'UPDATE' then
        if new.owner_id is distinct from old.owner_id then
            raise exception 'conversation owner is immutable' using errcode = '42501';
        end if;

        -- Existing identity rows cannot disappear and established bindings cannot change.
        for v_spec in
            select * from (values
                ('messages', 'message_id', array['conversation_id','session_id','role','request_id','created_at']::text[]),
                ('requests', 'request_id', array['conversation_id','session_id','message_id','created_at']::text[]),
                ('rounds', 'round_id', array[
                    'conversation_id','session_id','message_id','request_id','round','round_number',
                    'round_no','ordinal','round_ordinal','canonical_round_base',
                    'canonical_round_record_id','canonical_identity_key','created_at'
                ]::text[])
            ) as identity_fields(collection_name, id_field, immutable_fields)
        loop
            for v_old_row in
                select items.value from jsonb_array_elements(old.canonical_record -> v_spec.collection_name) as items(value)
            loop
                v_id := v_old_row ->> v_spec.id_field;
                select items.value into v_new_row
                from jsonb_array_elements(new.canonical_record -> v_spec.collection_name) as items(value)
                where items.value ->> v_spec.id_field = v_id
                limit 1;
                if not found then
                    raise exception 'canonical % history cannot be silently removed', v_spec.collection_name
                        using errcode = '22023';
                end if;
                foreach v_field in array v_spec.immutable_fields
                loop
                    if v_old_row ? v_field
                       and (v_old_row -> v_field) not in ('null'::jsonb, '""'::jsonb)
                       and (v_new_row -> v_field) is distinct from (v_old_row -> v_field) then
                        raise exception 'canonical % identity binding cannot be rewritten', v_spec.collection_name
                            using errcode = '22023';
                    end if;
                end loop;
            end loop;
        end loop;
    end if;

    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists council_conversations_guard_row on public.council_conversations;
create trigger council_conversations_guard_row
    before insert or update on public.council_conversations
    for each row execute function public.guard_council_conversation_row();

-- This is an internal trigger, not a callable RPC or privilege-elevating function.
revoke all on function public.guard_council_conversation_row() from public, anon, authenticated;

commit;
