-- Run against a disposable local Supabase database with pgTAP installed:
--   supabase test db
-- These tests are not run by the Python-only GitHub workflow yet; do not enable
-- application integration until this suite has been run against the target migration.
begin;
select plan(9);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at
) values
    ('00000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated',
     'council-owner-a@example.test', '', now(), now(), now()),
    ('00000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated',
     'council-owner-b@example.test', '', now(), now(), now())
on conflict (id) do nothing;

set local role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', true);
select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',
    true
);

select lives_ok(
    $$
    insert into public.council_conversations
        (conversation_id, owner_id, schema, canonical_record, checksum)
    values (
        'rls-conversation-a',
        '00000000-0000-0000-0000-00000000000a',
        'ai-council-supabase-conversation/v1',
        $record$
        {
          "conversation_id":"rls-conversation-a",
          "session_id":"session-a",
          "canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE",
          "messages":[{
            "message_id":"message-a",
            "conversation_id":"rls-conversation-a",
            "session_id":"session-a",
            "role":"user",
            "request_id":"request-a",
            "created_at":"2026-10-23T00:00:00Z",
            "content":"original"
          }],
          "requests":[{
            "request_id":"request-a",
            "conversation_id":"rls-conversation-a",
            "session_id":"session-a",
            "message_id":"message-a",
            "created_at":"2026-10-23T00:00:01Z",
            "state":"COMPLETED"
          }],
          "rounds":[{
            "round_id":"rls-conversation-a:request-a:r1",
            "conversation_id":"rls-conversation-a",
            "session_id":"session-a",
            "message_id":"message-a",
            "request_id":"request-a",
            "round":1,
            "round_number":1,
            "canonical_round_base":1,
            "canonical_round_record_id":"rls-conversation-a:request-a:r1",
            "canonical_identity_key":"rls-conversation-a:request-a:r1",
            "created_at":"2026-10-23T00:00:02Z",
            "status":"COMPLETED"
          }]
        }
        $record$::jsonb,
        repeat('0', 64)
    )
    $$,
    'Account A can insert a valid conversation owned by A'
);

select is(
    (select count(*)::integer from public.council_conversations where conversation_id = 'rls-conversation-a'),
    1,
    'Account A can read its own conversation'
);

select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', true);
select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-0000-0000-00000000000b","role":"authenticated"}',
    true
);

select is(
    (select count(*)::integer from public.council_conversations where conversation_id = 'rls-conversation-a'),
    0,
    'Account B cannot read Account A conversation'
);

select lives_ok(
    $
    update public.council_conversations
    set canonical_record = jsonb_set(canonical_record, '{messages,0,content}', '"tampered"'::jsonb)
    where conversation_id = 'rls-conversation-a'
    $,
    'Account B update of an unowned row is rejected by RLS'
);

select lives_ok(
    $
    delete from public.council_conversations
    where conversation_id = 'rls-conversation-a'
    $,
    'Account B delete of an unowned row is rejected by RLS'
);

select throws_ok(
    $$
    insert into public.council_conversations
        (conversation_id, owner_id, schema, canonical_record, checksum)
    values (
        'rls-owner-spoof',
        '00000000-0000-0000-0000-00000000000a',
        'ai-council-supabase-conversation/v1',
        '{"conversation_id":"rls-owner-spoof","canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE","messages":[],"requests":[],"rounds":[]}'::jsonb,
        repeat('0', 64)
    )
    $$,
    '42501',
    'conversation owner does not match the authenticated user',
    'Account B cannot insert a row attributed to Account A'
);

select ok(
    not has_table_privilege('anon', 'public.council_conversations', 'SELECT'),
    'Signed-out anon role has no table SELECT privilege'
);


select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', true);
select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',
    true
);

select is(
    (select count(*)::integer from public.council_conversations where conversation_id = 'rls-conversation-a'),
    1,
    'Account A still owns its row after Account B attempted writes'
);

select is(
    (select canonical_record #>> '{messages,0,content}' from public.council_conversations where conversation_id = 'rls-conversation-a'),
    'original',
    'Account A content remains unchanged after Account B attempted writes'
);

select * from finish();
rollback;
