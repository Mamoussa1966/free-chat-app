-- Authentication and authorization tests for the Cloudflare Worker admin gateway.
-- All user/operator fixtures and audit rows are rolled back at the end.
begin;
select plan(13);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at
) values
    ('00000000-0000-4000-8000-0000000000a1', 'authenticated', 'authenticated',
     'worker-admin-a@example.test', '', now(), now(), now()),
    ('00000000-0000-4000-8000-0000000000b2', 'authenticated', 'authenticated',
     'worker-admin-b@example.test', '', now(), now(), now())
on conflict (id) do nothing;

insert into private_cloudflare.worker_admin_operators(user_id, enabled, allowed_actions)
values (
    '00000000-0000-4000-8000-0000000000a1',
    true,
    array['inspect','deploy']::text[]
)
on conflict (user_id) do update set
    enabled = excluded.enabled,
    allowed_actions = excluded.allowed_actions;

select ok(
    not has_function_privilege(
        'anon',
        'public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)',
        'EXECUTE'
    ),
    'anon cannot execute the admin gateway'
);

select ok(
    not has_function_privilege(
        'service_role',
        'public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)',
        'EXECUTE'
    ),
    'service_role cannot execute the admin gateway'
);

select ok(
    has_function_privilege(
        'authenticated',
        'public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)',
        'EXECUTE'
    ),
    'authenticated can reach only the guarded public gateway'
);

select ok(
    (select prosecdef
       from pg_proc
      where oid = 'public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)'::regprocedure),
    'gateway is SECURITY DEFINER and has a fixed search_path'
);

select ok(
    not has_table_privilege(
        'authenticated',
        'private_cloudflare.worker_admin_operators',
        'SELECT'
    ),
    'authenticated cannot read the operator allow-list'
);

set local role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000000a1', true);
select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal1","is_anonymous":false}',
    true
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'list', null, '{}'::jsonb, null,
        '11111111-1111-4111-8111-111111111111'
    )->>'ok',
    'true',
    'enrolled operator can list allow-listed Workers'
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'list', null, '{}'::jsonb, null,
        '11111111-1111-4111-8111-111111111112'
    )->'result',
    '[]'::jsonb,
    'list returns an empty allow-list without calling Cloudflare'
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'register', 'nonexistent-worker',
        '{"environment":"test","allowed_operations":["inspect"],"allow_delete":false}'::jsonb,
        'REGISTER WORKER nonexistent-worker AS test',
        '11111111-1111-4111-8111-111111111113'
    )->>'reason',
    'operator_action_not_allowed',
    'operator cannot use actions absent from their own allow-list'
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'deploy', 'nonexistent-worker',
        '{"version_id":"22222222-2222-4222-8222-222222222222"}'::jsonb,
        'DEPLOY nonexistent-worker 22222222-2222-4222-8222-222222222222',
        '11111111-1111-4111-8111-111111111114'
    )->>'reason',
    'aal2_required',
    'write/deploy operations require an AAL2 session'
);

select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000000b2', true);
select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-4000-8000-0000000000b2","role":"authenticated","aal":"aal2","is_anonymous":false}',
    true
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'list', null, '{}'::jsonb, null,
        '11111111-1111-4111-8111-111111111115'
    )->>'reason',
    'operator_not_enrolled',
    'a different authenticated user cannot use the gateway without enrollment'
);

select set_config('request.jwt.claim.sub', '00000000-0000-4000-8000-0000000000a1', true);
select set_config(
    'request.jwt.claims',
    '{"sub":"00000000-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal2","is_anonymous":true}',
    true
);

select is(
    public.cloudflare_worker_admin_dispatch(
        'list', null, '{}'::jsonb, null,
        '11111111-1111-4111-8111-111111111116'
    )->>'code',
    'authenticated_user_required',
    'anonymous Supabase users are never operators'
);

reset role;

select is(
    (
      select count(*)::integer
        from private_cloudflare.worker_admin_audit
       where operation like 'gateway_denied:%'
         and actor_user_id in (
           '00000000-0000-4000-8000-0000000000a1'::uuid,
           '00000000-0000-4000-8000-0000000000b2'::uuid
         )
         and interface = 'supabase_authenticated_gateway'
    ),
    3,
    'denied authenticated requests are recorded with actor and request metadata'
);

select ok(
    exists (
      select 1 from pg_trigger
       where tgname = 'worker_admin_audit_set_context'
         and not tgisinternal
    ),
    'audit context trigger is installed'
);

select * from finish();
rollback;
