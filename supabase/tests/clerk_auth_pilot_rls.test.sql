-- Isolated Clerk issuer/subject RLS test.
-- Run via: supabase test db --local
-- All rows and claim overrides are rolled back at the end.
begin;
select plan(17);

select ok(
  (select relrowsecurity
   from pg_class
   where oid = 'public.clerk_auth_pilot_records'::regclass),
  'Clerk pilot table has row-level security enabled'
);

select ok(
  not has_table_privilege('anon', 'public.clerk_auth_pilot_records', 'SELECT'),
  'Anonymous role has no SELECT privilege on the Clerk pilot table'
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"iss":"https://dear-hermit-1240.clerk.accounts.dev","sub":"user_pilot_a","role":"authenticated"}',
  true
);
select set_config('request.jwt.claim.sub', 'user_pilot_a', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

select lives_ok(
  $$
    insert into public.clerk_auth_pilot_records
      (owner_subject, record_key, record_payload)
    values ('user_pilot_a', 'record-a', '{"value":"original-a"}'::jsonb)
  $$,
  'Clerk user A can insert a row owned by A'
);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records where record_key = 'record-a'),
  1,
  'Clerk user A can read its own row'
);

select set_config(
  'request.jwt.claims',
  '{"iss":"https://dear-hermit-1240.clerk.accounts.dev","sub":"user_pilot_b","role":"authenticated"}',
  true
);
select set_config('request.jwt.claim.sub', 'user_pilot_b', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records where record_key = 'record-a'),
  0,
  'Clerk user B cannot read A rows'
);

select lives_ok(
  $$
    update public.clerk_auth_pilot_records
    set record_payload = '{"value":"tampered-by-b"}'::jsonb
    where record_key = 'record-a'
  $$,
  'Clerk user B update of A rows is filtered by RLS'
);

select lives_ok(
  $$
    delete from public.clerk_auth_pilot_records
    where record_key = 'record-a'
  $$,
  'Clerk user B delete of A rows is filtered by RLS'
);

select throws_ok(
  $$
    insert into public.clerk_auth_pilot_records
      (owner_subject, record_key, record_payload)
    values ('user_pilot_a', 'spoofed-a', '{}'::jsonb)
  $$,
  '42501',
  'new row violates row-level security policy for table "clerk_auth_pilot_records"',
  'Clerk user B cannot insert a row claiming A as its owner'
);

select lives_ok(
  $$
    insert into public.clerk_auth_pilot_records
      (owner_subject, record_key, record_payload)
    values ('user_pilot_b', 'record-b', '{"value":"owned-by-b"}'::jsonb)
  $$,
  'Clerk user B can insert a row owned by B'
);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records where record_key = 'record-b'),
  1,
  'Clerk user B can read its own row'
);

select set_config(
  'request.jwt.claims',
  '{"iss":"https://pidcepvwsezdrlhxqksg.supabase.co/auth/v1","sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',
  true
);
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records),
  0,
  'Native Supabase Auth issuer cannot read Clerk pilot rows'
);

select throws_ok(
  $$
    insert into public.clerk_auth_pilot_records
      (owner_subject, record_key, record_payload)
    values ('00000000-0000-0000-0000-00000000000a', 'native-auth-row', '{}'::jsonb)
  $$,
  '42501',
  'new row violates row-level security policy for table "clerk_auth_pilot_records"',
  'Native Supabase Auth issuer cannot insert into the Clerk pilot table'
);

select set_config(
  'request.jwt.claims',
  '{"iss":"https://wrong-issuer.example.test","sub":"user_pilot_b","role":"authenticated"}',
  true
);
select set_config('request.jwt.claim.sub', 'user_pilot_b', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records),
  0,
  'An untrusted issuer cannot read Clerk pilot rows'
);

select throws_ok(
  $$
    insert into public.clerk_auth_pilot_records
      (owner_subject, record_key, record_payload)
    values ('user_pilot_b', 'wrong-issuer-row', '{}'::jsonb)
  $$,
  '42501',
  'new row violates row-level security policy for table "clerk_auth_pilot_records"',
  'An untrusted issuer cannot insert into the Clerk pilot table'
);

select set_config(
  'request.jwt.claims',
  '{"iss":"https://dear-hermit-1240.clerk.accounts.dev","sub":"user_pilot_a","role":"authenticated"}',
  true
);
select set_config('request.jwt.claim.sub', 'user_pilot_a', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records where record_key = 'record-a'),
  1,
  'Clerk user A still reads its own original row'
);

select is(
  (select record_payload ->> 'value'
   from public.clerk_auth_pilot_records
   where record_key = 'record-a'),
  'original-a',
  'User B update and delete attempts did not modify or remove A data'
);

select is(
  (select count(*)::integer from public.clerk_auth_pilot_records where record_key = 'record-b'),
  0,
  'Clerk user A cannot read B rows'
);

select * from finish();
rollback;
