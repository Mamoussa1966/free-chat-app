-- Enforce monotonic terminal states for canonical Request and Round records.
-- The existing row guard validates ownership, shape, bindings, and append-only IDs.
-- This second UPDATE trigger rejects stale snapshots that try to roll back a
-- terminal Request.state or Round.status after a concurrent writer has committed.

begin;

create or replace function public.guard_council_conversation_terminal_lifecycle()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_spec record;
    v_old_row jsonb;
    v_new_row jsonb;
    v_id text;
    v_old_state text;
    v_new_state text;
begin
    if tg_op <> 'UPDATE' then
        return new;
    end if;

    for v_spec in
        select *
        from (values
            ('requests', 'request_id', 'state'),
            ('rounds', 'round_id', 'status')
        ) as lifecycle_fields(collection_name, id_field, state_field)
    loop
        for v_old_row in
            select old_items.value
            from pg_catalog.jsonb_array_elements(
                old.canonical_record -> v_spec.collection_name
            ) as old_items(value)
        loop
            v_id := v_old_row ->> v_spec.id_field;

            select new_items.value
              into v_new_row
            from pg_catalog.jsonb_array_elements(
                new.canonical_record -> v_spec.collection_name
            ) as new_items(value)
            where new_items.value ->> v_spec.id_field = v_id
            limit 1;

            if not found then
                raise exception 'canonical % history cannot be silently removed',
                    v_spec.collection_name
                    using errcode = '23514';
            end if;

            v_old_state := pg_catalog.upper(
                pg_catalog.btrim(coalesce(v_old_row ->> v_spec.state_field, ''))
            );
            v_new_state := pg_catalog.upper(
                pg_catalog.btrim(coalesce(v_new_row ->> v_spec.state_field, ''))
            );

            if v_old_state = any (array[
                'COMPLETED',
                'SUCCEEDED',
                'FAILED',
                'REJECTED',
                'CANCELLED',
                'CANCELED',
                'ABORTED',
                'EXPIRED'
            ]::text[])
            and v_new_state is distinct from v_old_state then
                raise exception 'canonical % terminal lifecycle state cannot be rewritten',
                    v_spec.collection_name
                    using errcode = '23514';
            end if;
        end loop;
    end loop;

    return new;
end;
$$;

drop trigger if exists council_conversations_terminal_lifecycle_guard
    on public.council_conversations;

create trigger council_conversations_terminal_lifecycle_guard
    before update on public.council_conversations
    for each row
    execute function public.guard_council_conversation_terminal_lifecycle();

-- The function is an internal trigger, not a client-callable RPC.
revoke all on function public.guard_council_conversation_terminal_lifecycle()
    from public, anon, authenticated;

commit;
