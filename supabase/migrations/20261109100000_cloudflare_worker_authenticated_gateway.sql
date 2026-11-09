-- Authenticated Cloudflare Worker Admin Gateway
-- Adds a narrowly scoped public RPC + authenticated Edge Function boundary.
-- No service-role or secret API key is used by the Streamlit application.
-- Operator enrollment is intentionally empty: a database owner must add an
-- explicit Auth user UUID and approved actions before any user can administer Workers.

alter table private_cloudflare.worker_admin_audit
  add column if not exists actor_user_id uuid,
  add column if not exists request_id uuid,
  add column if not exists interface text not null default 'direct_database';

create table if not exists private_cloudflare.worker_admin_operators (
  user_id uuid primary key references auth.users(id) on delete restrict,
  enabled boolean not null default true,
  allowed_actions text[] not null default array['inspect']::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid,
  constraint worker_admin_operator_actions_check check (
    allowed_actions <@ array[
      'inspect','register','refresh_versions','update_metadata',
      'upload_version','deploy','rollback','set_policy'
    ]::text[]
  )
);

alter table private_cloudflare.worker_admin_operators
  add column if not exists updated_by uuid;

do $constraints$
begin
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'private_cloudflare.worker_admin_operators'::regclass
       and conname = 'worker_admin_operators_created_by_fkey'
  ) then
    alter table private_cloudflare.worker_admin_operators
      add constraint worker_admin_operators_created_by_fkey
      foreign key (created_by) references auth.users(id) on delete restrict;
  end if;
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'private_cloudflare.worker_admin_operators'::regclass
       and conname = 'worker_admin_operators_updated_by_fkey'
  ) then
    alter table private_cloudflare.worker_admin_operators
      add constraint worker_admin_operators_updated_by_fkey
      foreign key (updated_by) references auth.users(id) on delete restrict;
  end if;
end;
$constraints$;

alter table private_cloudflare.worker_admin_operators
  alter column created_by set not null;

create or replace function private_cloudflare.worker_admin_operator_audit()
returns trigger
language plpgsql
set search_path to 'pg_catalog', 'private_cloudflare'
as $function$
declare
  v_actor uuid;
  v_user_id uuid;
  v_operation text;
  v_summary jsonb;
begin
  if tg_op = 'DELETE' then
    raise exception 'Operator records cannot be deleted; disable the operator to preserve the audit history';
  end if;

  if tg_op = 'INSERT' then
    v_actor := new.created_by;
    if v_actor is null then
      raise exception 'Operator enrollment requires a verified creator UUID';
    end if;
    v_user_id := new.user_id;
    v_operation := 'operator_enrolled';
    v_summary := jsonb_build_object(
      'user_id', new.user_id,
      'enabled', new.enabled,
      'allowed_actions', new.allowed_actions
    );
  else
    v_actor := new.updated_by;
    if v_actor is null then
      raise exception 'Operator updates require an approving updated_by UUID';
    end if;
    v_user_id := new.user_id;
    v_operation := 'operator_policy_updated';
    v_summary := jsonb_build_object(
      'user_id', new.user_id,
      'previous_enabled', old.enabled,
      'enabled', new.enabled,
      'previous_allowed_actions', old.allowed_actions,
      'allowed_actions', new.allowed_actions
    );
  end if;

  perform set_config('app.worker_admin.actor_user_id', coalesce(v_actor::text, ''), true);
  perform set_config('app.worker_admin.request_id', gen_random_uuid()::text, true);
  perform set_config('app.worker_admin.interface', 'operator_management', true);

  insert into private_cloudflare.worker_admin_audit(
    worker_name, operation, http_status, api_success, result_summary
  ) values (
    '__operators__', v_operation, 200, true, v_summary
  );

  if tg_op = 'INSERT' then
    return new;
  end if;
  return new;
end;
$function$;

drop trigger if exists worker_admin_operator_audit
  on private_cloudflare.worker_admin_operators;
create trigger worker_admin_operator_audit
after insert or update on private_cloudflare.worker_admin_operators
for each row execute function private_cloudflare.worker_admin_operator_audit();

drop trigger if exists worker_admin_operator_no_delete
  on private_cloudflare.worker_admin_operators;
create trigger worker_admin_operator_no_delete
before delete on private_cloudflare.worker_admin_operators
for each row execute function private_cloudflare.worker_admin_operator_audit();

revoke all on function private_cloudflare.worker_admin_operator_audit()
  from public, anon, authenticated, service_role;

alter table private_cloudflare.worker_admin_operators enable row level security;
alter table private_cloudflare.worker_admin_operators force row level security;

drop policy if exists worker_admin_operators_postgres_only
  on private_cloudflare.worker_admin_operators;
create policy worker_admin_operators_postgres_only
  on private_cloudflare.worker_admin_operators
  for all to postgres using (true) with check (true);

revoke all on private_cloudflare.worker_admin_operators
  from public, anon, authenticated, service_role;

create or replace function private_cloudflare.worker_admin_audit_set_context()
returns trigger
language plpgsql
set search_path to 'pg_catalog'
as $function$
begin
  new.actor_user_id := nullif(current_setting('app.worker_admin.actor_user_id', true), '')::uuid;
  new.request_id := nullif(current_setting('app.worker_admin.request_id', true), '')::uuid;
  new.interface := coalesce(
    nullif(current_setting('app.worker_admin.interface', true), ''),
    'direct_database'
  );
  return new;
end;
$function$;

drop trigger if exists worker_admin_audit_set_context
  on private_cloudflare.worker_admin_audit;
create trigger worker_admin_audit_set_context
before insert on private_cloudflare.worker_admin_audit
for each row execute function private_cloudflare.worker_admin_audit_set_context();

create or replace function public.cloudflare_worker_admin_dispatch(
  p_operation text,
  p_worker_name text default null,
  p_payload jsonb default '{}'::jsonb,
  p_confirmation text default null,
  p_request_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'auth', 'private_cloudflare'
as $function$
declare
  v_user_id uuid;
  v_claims jsonb;
  v_operator private_cloudflare.worker_admin_operators%rowtype;
  v_request_id uuid := coalesce(p_request_id, gen_random_uuid());
  v_payload jsonb := coalesce(p_payload, '{}'::jsonb);
  v_result jsonb;
  v_required_action text;
  v_ops text[];
  v_tags text[];
  v_environment text;
  v_allow_delete boolean;
  v_version_id uuid;
  v_compatibility_date date;
  v_denial_reason text;
begin
  v_user_id := auth.uid();
  v_claims := auth.jwt();

  if v_user_id is null
     or coalesce(v_claims->>'role', '') <> 'authenticated'
     or coalesce(v_claims->>'is_anonymous', 'false') = 'true' then
    return jsonb_build_object('ok', false, 'code', 'authenticated_user_required');
  end if;

  perform set_config('app.worker_admin.actor_user_id', v_user_id::text, true);
  perform set_config('app.worker_admin.request_id', v_request_id::text, true);
  perform set_config('app.worker_admin.interface', 'supabase_authenticated_gateway', true);

  v_required_action := case when p_operation = 'list' then 'inspect' else p_operation end;

  if coalesce(p_operation, '') not in (
    'list','register','refresh_versions','update_metadata',
    'upload_version','deploy','rollback','set_policy'
  ) then
    v_denial_reason := 'unsupported_operation';
  else
    select * into v_operator
      from private_cloudflare.worker_admin_operators
     where user_id = v_user_id and enabled;

    if not found then
      v_denial_reason := 'operator_not_enrolled';
    elsif not (v_required_action = any(v_operator.allowed_actions)) then
      v_denial_reason := 'operator_action_not_allowed';
    elsif p_operation <> 'list' and coalesce(v_claims->>'aal', 'aal1') <> 'aal2' then
      v_denial_reason := 'aal2_required';
    end if;
  end if;

  if v_denial_reason is not null then
    insert into private_cloudflare.worker_admin_audit(
      worker_name, operation, http_status, api_success, result_summary
    ) values (
      coalesce(nullif(p_worker_name, ''), '__gateway__'),
      'gateway_denied:' || coalesce(nullif(p_operation, ''), 'unknown'),
      403, false,
      jsonb_build_object('reason', v_denial_reason, 'request_id', v_request_id)
    );
    return jsonb_build_object(
      'ok', false, 'code', 'admin_access_denied',
      'reason', v_denial_reason, 'request_id', v_request_id
    );
  end if;

  if jsonb_typeof(v_payload) <> 'object'
     or octet_length(v_payload::text) > 280000 then
    return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
  end if;

  if p_operation = 'list' then
    if p_worker_name is not null or v_payload <> '{}'::jsonb then
      return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
    end if;
    v_result := private_cloudflare.worker_admin_list();

  else
    if p_worker_name is null or p_worker_name !~ '^[a-z0-9][a-z0-9-]{0,62}$' then
      return jsonb_build_object('ok', false, 'code', 'invalid_worker_name', 'request_id', v_request_id);
    end if;

    case p_operation
      when 'register' then
        if (v_payload - array['environment','allowed_operations','allow_delete']::text[]) <> '{}'::jsonb
           or coalesce(jsonb_typeof(v_payload->'allowed_operations'), '') <> 'array'
           or nullif(v_payload->>'environment','') is null then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_environment := v_payload->>'environment';
        if p_confirmation is distinct from 'REGISTER WORKER ' || p_worker_name || ' AS ' || v_environment then
          return jsonb_build_object('ok', false, 'code', 'confirmation_mismatch', 'request_id', v_request_id);
        end if;
        select array_agg(value) into v_ops
          from jsonb_array_elements_text(v_payload->'allowed_operations') as x(value);
        v_allow_delete := coalesce((v_payload->>'allow_delete')::boolean, false);
        if v_allow_delete or 'delete' = any(coalesce(v_ops, array[]::text[])) then
          return jsonb_build_object('ok', false, 'code', 'delete_not_supported_by_gateway', 'request_id', v_request_id);
        end if;
        v_result := private_cloudflare.worker_admin_register(
          p_worker_name, v_environment, coalesce(v_ops, array['inspect']::text[]), v_allow_delete
        );

      when 'refresh_versions' then
        if v_payload <> '{}'::jsonb or p_confirmation is not null then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_result := private_cloudflare.worker_admin_refresh_versions(p_worker_name);

      when 'update_metadata' then
        if (v_payload - array['tags']::text[]) <> '{}'::jsonb
           or coalesce(jsonb_typeof(v_payload->'tags'), '') <> 'array' then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        select array_agg(value) into v_tags
          from jsonb_array_elements_text(v_payload->'tags') as x(value);
        v_result := private_cloudflare.worker_admin_update_tags(
          p_worker_name, coalesce(v_tags, array[]::text[]), p_confirmation
        );

      when 'upload_version' then
        if (v_payload - array['module_js','message','compatibility_date']::text[]) <> '{}'::jsonb
           or nullif(v_payload->>'module_js','') is null
           or nullif(v_payload->>'message','') is null then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_compatibility_date := coalesce(
          nullif(v_payload->>'compatibility_date','')::date, current_date
        );
        v_result := private_cloudflare.worker_admin_upload_module_version(
          p_worker_name, v_payload->>'module_js', v_payload->>'message',
          p_confirmation, v_compatibility_date
        );

      when 'deploy' then
        if (v_payload - array['version_id']::text[]) <> '{}'::jsonb
           or nullif(v_payload->>'version_id','') is null then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_version_id := (v_payload->>'version_id')::uuid;
        v_result := private_cloudflare.worker_admin_deploy(
          p_worker_name, v_version_id, p_confirmation
        );

      when 'rollback' then
        if (v_payload - array['version_id']::text[]) <> '{}'::jsonb
           or nullif(v_payload->>'version_id','') is null then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_version_id := (v_payload->>'version_id')::uuid;
        v_result := private_cloudflare.worker_admin_rollback(
          p_worker_name, v_version_id, p_confirmation
        );

      when 'set_policy' then
        if (v_payload - array['environment','allowed_operations','allow_delete']::text[]) <> '{}'::jsonb
           or nullif(v_payload->>'environment','') is null
           or coalesce(jsonb_typeof(v_payload->'allowed_operations'), '') <> 'array' then
          return jsonb_build_object('ok', false, 'code', 'invalid_payload', 'request_id', v_request_id);
        end if;
        v_environment := v_payload->>'environment';
        select array_agg(value) into v_ops
          from jsonb_array_elements_text(v_payload->'allowed_operations') as x(value);
        v_allow_delete := coalesce((v_payload->>'allow_delete')::boolean, false);
        if v_allow_delete or 'delete' = any(coalesce(v_ops, array[]::text[])) then
          return jsonb_build_object('ok', false, 'code', 'delete_not_supported_by_gateway', 'request_id', v_request_id);
        end if;
        v_result := private_cloudflare.worker_admin_set_policy(
          p_worker_name, v_environment, coalesce(v_ops, array[]::text[]),
          v_allow_delete, p_confirmation
        );

      else
        return jsonb_build_object('ok', false, 'code', 'unsupported_operation', 'request_id', v_request_id);
    end case;
  end if;

  return jsonb_build_object(
    'ok', coalesce((v_result->>'ok')::boolean, true),
    'request_id', v_request_id,
    'result', v_result
  );
end;
$function$;

revoke all on function public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)
  from public, anon, service_role;
grant execute on function public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid)
  to authenticated;

revoke all on function private_cloudflare.worker_admin_audit_set_context()
  from public, anon, authenticated, service_role;

comment on table private_cloudflare.worker_admin_operators is
  'Explicit per-user operator allow-list. Empty by default; only postgres may enroll or change operators.';
comment on function public.cloudflare_worker_admin_dispatch(text,text,jsonb,text,uuid) is
  'Authenticated, AAL2-gated gateway to allow-listed Cloudflare Worker operations. Never uses service_role.';
