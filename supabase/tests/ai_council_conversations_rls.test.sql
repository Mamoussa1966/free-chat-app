begin;

select plan(8);

-- These users and their data are rolled back at the end of the test.
insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at)
values
(
    '11111111-1111-4111-8111-111111111111',
    'authenticated',
    'authenticated',
    'council-owner-a@example.test',
    '',
    pg_catalog.now(),
    pg_catalog.now(),
    pg_catalog.now()
),
(
    '22222222-2222-4222-8222-222222222222',
    'authenticated',
    'authenticated',
    'council-owner-b@example.test',
    '',
    pg_catalog.now(),
    pg_catalog.now(),
    pg_catalog.now()
);

set local role authenticated;
select pg_catalog.set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
select pg_catalog.set_config('request.jwt.claim.role', 'authenticated', true);

insert into public.ai_council_conversations (
    conversation_id, owner_id, canonical_record_json, snapshot_sha256
) values (
    'rls-test-conversation',
    '11111111-1111-4111-8111-111111111111',
    '{"conversation_id":"rls-test-conversation","canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE","messages":[],"requests":[],"rounds":[]}',
    repeat('a', 64)
);

select is(
    (select count(*)::integer from public.ai_council_conversations where conversation_id = 'rls-test-conversation'),
    1,
    'owner A can read the conversation it created'
);

select pg_catalog.set_config('request.jwt.claim.sub', '22222222-2222-4222-8222-222222222222', true);

select is(
    (select count(*)::integer from public.ai_council_conversations where conversation_id = 'rls-test-conversation'),
    0,
    'owner B cannot read owner A conversation'
);

select is(
    (with changed as (
        update public.ai_council_conversations
        set canonical_record_json = '{"tampered":true}'
        where conversation_id = 'rls-test-conversation'
        returning 1
    ) select count(*)::integer from changed),
    0,
    'owner B cannot update owner A conversation'
);

select is(
    (with removed as (
        delete from public.ai_council_conversations
        where conversation_id = 'rls-test-conversation'
        returning 1
    ) select count(*)::integer from removed),
    0,
    'owner B cannot delete owner A conversation'
);

select throws_ok(
    $$
        insert into public.ai_council_conversations (
            conversation_id, owner_id, canonical_record_json, snapshot_sha256
        ) values (
            'rls-test-forged-owner',
            '11111111-1111-4111-8111-111111111111',
            '{"conversation_id":"rls-test-forged-owner","canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE","messages":[],"requests":[],"rounds":[]}',
            repeat('b', 64)
        )
    $$,
    '42501',
    null,
    'owner B cannot insert a row for owner A'
);

select pg_catalog.set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);

select is(
    (select canonical_record_json from public.ai_council_conversations where conversation_id = 'rls-test-conversation'),
    '{"conversation_id":"rls-test-conversation","canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE","messages":[],"requests":[],"rounds":[]}',
    'rejected cross-account operations leave owner A data unchanged'
);

select is(
    (with removed as (
        delete from public.ai_council_conversations
        where conversation_id = 'rls-test-conversation'
        returning 1
    ) select count(*)::integer from removed),
    1,
    'owner A can delete its own conversation'
);

select is(
    (select count(*)::integer from public.ai_council_conversations where conversation_id = 'rls-test-conversation'),
    0,
    'deleted owner A conversation is no longer readable'
);

select * from finish();
rollback;
