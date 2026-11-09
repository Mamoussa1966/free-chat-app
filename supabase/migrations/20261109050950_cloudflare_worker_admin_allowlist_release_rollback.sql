-- Cloudflare Worker Admin Bridge
-- Self-contained incremental Supabase migration for the test project.
-- Per-Worker allow-list; exact confirmations; production protections; audited deployment and rollback.
-- Private schema and tables are not exposed to client roles. RLS is enabled as defense in depth.

create schema if not exists extensions;
create extension if not exists http with schema extensions;
create schema if not exists vault;
create extension if not exists supabase_vault with schema vault;
create schema if not exists private_cloudflare;

create table if not exists private_cloudflare.worker_admin_allowlist (
  worker_name text primary key, worker_id text not null unique,
  environment text not null check (environment in ('production','staging','development','test')),
  enabled boolean not null default true,
  allowed_operations text[] not null default array['inspect']::text[],
  production_protected boolean not null default true,
  allow_delete boolean not null default false,
  supports_simple_module_upload boolean not null default false,
  active_version_ids uuid[] not null default array[]::uuid[],
  registered_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  last_reconciled_at timestamptz, deleted_at timestamptz,
  check (allowed_operations <@ array['inspect','update_metadata','upload_version','deploy','rollback','delete']::text[]),
  check (environment <> 'production' or (production_protected and not allow_delete and not ('delete'=any(allowed_operations)))),
  check (allow_delete = ('delete'=any(allowed_operations))),
  check (environment <> 'production' or production_protected),
  constraint worker_admin_delete_test_only check (not allow_delete or environment='test')
);

create table if not exists private_cloudflare.worker_admin_versions (
  worker_name text not null references private_cloudflare.worker_admin_allowlist(worker_name),
  version_id uuid not null, version_number integer,
  origin text not null default 'cloudflare' check (origin in ('cloudflare','bridge')),
  was_deployed boolean not null default false, is_currently_deployed boolean not null default false,
  created_on timestamptz, last_deployed_at timestamptz,
  annotations jsonb not null default '{}'::jsonb, first_seen_at timestamptz not null default now(),
  primary key (worker_name,version_id)
);

create table if not exists private_cloudflare.worker_admin_audit (
  audit_id bigint generated always as identity primary key, worker_name text not null,
  worker_id text, operation text not null, version_id uuid, http_status integer,
  api_success boolean, result_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table private_cloudflare.worker_admin_allowlist enable row level security;
alter table private_cloudflare.worker_admin_versions enable row level security;
alter table private_cloudflare.worker_admin_audit enable row level security;

create index if not exists worker_admin_versions_worker_name_idx on private_cloudflare.worker_admin_versions(worker_name);
create index if not exists worker_admin_audit_worker_created_idx on private_cloudflare.worker_admin_audit(worker_name,created_at desc);

revoke all on private_cloudflare.worker_admin_allowlist from public,anon,authenticated,service_role;
revoke all on private_cloudflare.worker_admin_versions from public,anon,authenticated,service_role;
revoke all on private_cloudflare.worker_admin_audit from public,anon,authenticated,service_role;
revoke all on schema private_cloudflare from public,anon,authenticated,service_role;
;

CREATE OR REPLACE FUNCTION private_cloudflare.request(p_method text, p_path text, p_body jsonb DEFAULT NULL::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'extensions', 'vault'
AS $function$
declare
  v_token text;
  v_response extensions.http_response;
  v_method text := upper(btrim(coalesce(p_method, '')));
  v_prefix constant text := '/accounts/1171975142d29fc55425b752629bb8bd/';
begin
  if v_method <> 'GET' then
    raise exception 'Cloudflare bridge is read-only: GET only';
  end if;

  if p_body is not null then
    raise exception 'Cloudflare bridge does not accept request bodies';
  end if;

  if p_path is null
     or left(p_path, length(v_prefix)) <> v_prefix
     or position('..' in p_path) > 0
     or position('://' in p_path) > 0
     or position('#' in p_path) > 0
     or position(chr(10) in p_path) > 0
     or position(chr(13) in p_path) > 0 then
    raise exception 'Path is outside the allowed Cloudflare account scope';
  end if;

  select decrypted_secret
    into v_token
    from vault.decrypted_secrets
   where name = 'cloudflare_account_api_token'
   limit 1;

  if v_token is null or length(v_token) < 20 then
    raise exception 'Cloudflare API token is not configured in Supabase Vault';
  end if;

  select *
    into v_response
    from extensions.http(
      row(
        'GET'::extensions.http_method,
        'https://api.cloudflare.com/client/v4' || p_path,
        array[
          row('Authorization', 'Bearer ' || v_token)::extensions.http_header,
          row('Accept', 'application/json')::extensions.http_header
        ],
        null,
        null
      )::extensions.http_request
    );

  return jsonb_build_object(
    'status', v_response.status,
    'content_type', v_response.content_type,
    'body', v_response.content
  );
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare._worker_admin_http(p_method text, p_path text, p_body jsonb DEFAULT NULL::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'extensions', 'vault', 'private_cloudflare'
AS $function$
declare
  v_token text;
  v_response extensions.http_response;
  v_method text := upper(btrim(coalesce(p_method,'')));
  v_prefix constant text := '/accounts/1171975142d29fc55425b752629bb8bd/';
  v_target private_cloudflare.worker_admin_allowlist%rowtype;
  v_worker_name text;
  v_worker_id text;
  v_version_id uuid;
  v_base_path text;
  v_body jsonb;
  v_allowed boolean := false;
begin
  if v_method not in ('POST','PATCH','DELETE') then
    raise exception 'Worker admin bridge supports only the explicitly routed POST/PATCH/DELETE operations';
  end if;
  if p_path is null or left(p_path,length(v_prefix))<>v_prefix
     or position('..' in p_path)>0 or position('://' in p_path)>0
     or position('#' in p_path)>0 or position(chr(10) in p_path)>0
     or position(chr(13) in p_path)>0 then
    raise exception 'Cloudflare request path is outside the fixed account scope';
  end if;

  if v_method='POST'
     and position('?deploy=false' in p_path)>0
     and right(p_path,13)='?deploy=false' then
    v_base_path := left(p_path,length(p_path)-13);
    if v_base_path ~ ('^' || v_prefix || 'workers/workers/[a-f0-9]{32}/versions$')
       and p_body is not null
       and (p_body - array['main_module','modules','compatibility_date','annotations']::text[])='{}'::jsonb
       and p_body->>'main_module'='index.js'
       and jsonb_typeof(p_body->'modules')='array'
       and jsonb_array_length(p_body->'modules')=1 then
      v_worker_id := regexp_replace(v_base_path, '^.*/workers/([^/]+)/versions$', '\1');
      select * into v_target from private_cloudflare.worker_admin_allowlist
       where worker_id=v_worker_id and enabled and deleted_at is null;
      v_allowed := found and 'upload_version'=any(v_target.allowed_operations)
                   and v_target.supports_simple_module_upload;
    end if;
  elsif v_method='POST'
        and p_path ~ ('^' || v_prefix || 'workers/scripts/[a-z0-9-]{1,63}/deployments$')
        and p_body is not null
        and (p_body - array['strategy','versions','annotations']::text[])='{}'::jsonb
        and p_body->>'strategy'='percentage'
        and jsonb_typeof(p_body->'versions')='array'
        and jsonb_array_length(p_body->'versions')=1
        and (p_body->'versions'->0->>'percentage')::numeric=100 then
    v_worker_name := regexp_replace(p_path, '^.*/workers/scripts/([^/]+)/deployments$', '\1');
    v_version_id := nullif(p_body->'versions'->0->>'version_id','')::uuid;
    select * into v_target from private_cloudflare.worker_admin_allowlist
     where worker_name=v_worker_name and enabled and deleted_at is null;
    if found and (
       ('deploy'=any(v_target.allowed_operations) and exists(
          select 1 from private_cloudflare.worker_admin_versions v
           where v.worker_name=v_worker_name and v.version_id=v_version_id and not v.was_deployed
       ))
       or
       ('rollback'=any(v_target.allowed_operations) and exists(
          select 1 from private_cloudflare.worker_admin_versions v
           where v.worker_name=v_worker_name and v.version_id=v_version_id and v.was_deployed
       ))
    ) then v_allowed := true; end if;
  elsif v_method='PATCH'
        and p_path ~ ('^' || v_prefix || 'workers/workers/[a-f0-9]{32}$')
        and p_body is not null
        and (p_body - array['tags']::text[])='{}'::jsonb
        and jsonb_typeof(p_body->'tags')='array' then
    v_worker_id := regexp_replace(p_path, '^.*/workers/([^/]+)$', '\1');
    select * into v_target from private_cloudflare.worker_admin_allowlist
     where worker_id=v_worker_id and enabled and deleted_at is null;
    v_allowed := found and 'update_metadata'=any(v_target.allowed_operations)
                 and not v_target.production_protected;
  elsif v_method='DELETE'
        and p_path ~ ('^' || v_prefix || 'workers/workers/[a-f0-9]{32}$')
        and p_body is null then
    v_worker_id := regexp_replace(p_path, '^.*/workers/([^/]+)$', '\1');
    select * into v_target from private_cloudflare.worker_admin_allowlist
     where worker_id=v_worker_id and enabled and deleted_at is null;
    v_allowed := found and 'delete'=any(v_target.allowed_operations)
                 and v_target.allow_delete and not v_target.production_protected
                 and v_target.environment='test';
  end if;

  if not v_allowed then
    raise exception 'Worker operation blocked: resource is not allowlisted or policy does not permit this operation';
  end if;

  select decrypted_secret into v_token
    from vault.decrypted_secrets where name='cloudflare_account_api_token' limit 1;
  if v_token is null or length(v_token)<20 then
    raise exception 'Cloudflare API token is not configured in Supabase Vault';
  end if;

  select * into v_response from extensions.http(
    row(
      v_method::extensions.http_method,
      'https://api.cloudflare.com/client/v4'||p_path,
      array[
        row('Authorization','Bearer '||v_token)::extensions.http_header,
        row('Accept','application/json')::extensions.http_header,
        row('Content-Type','application/json')::extensions.http_header
      ],
      case when p_body is null then null else 'application/json' end,
      case when p_body is null then null else p_body::text end
    )::extensions.http_request
  );
  begin
    v_body:=v_response.content::jsonb;
  exception when others then
    v_body:=jsonb_build_object('raw_response',left(coalesce(v_response.content,''),1500));
  end;
  return jsonb_build_object('status',v_response.status,'content_type',v_response.content_type,'body',v_body);
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_prevent_audit_mutation()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
begin
  raise exception 'Cloudflare Worker audit records are append-only; UPDATE and DELETE are prohibited';
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_register(p_worker_name text, p_environment text DEFAULT 'production'::text, p_allowed_operations text[] DEFAULT ARRAY['inspect'::text], p_allow_delete boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare
  v_list jsonb; v_list_body jsonb; v_item jsonb; v_worker_id text;
  v_detail jsonb; v_detail_body jsonb; v_versions jsonb; v_versions_body jsonb;
  v_deployments jsonb; v_deployments_body jsonb; v_settings jsonb; v_settings_body jsonb;
  v_support_upload boolean := false; v_current uuid[]; v_id uuid; v_v jsonb;
  v_was_deployed boolean; v_active boolean; v_version_count integer:=0;
  v_refs jsonb; v_ref record; v_protected boolean;
begin
  if p_worker_name is null or p_worker_name !~ '^[a-z0-9][a-z0-9-]{0,62}$' then
    raise exception 'Worker name format is invalid';
  end if;
  if p_environment not in ('production','staging','development','test') then
    raise exception 'Environment must be production, staging, development, or test';
  end if;
  if p_allowed_operations is null or cardinality(p_allowed_operations)=0
     or not (p_allowed_operations <@ array['inspect','update_metadata','upload_version','deploy','rollback','delete']::text[]) then
    raise exception 'Allowed operations contain an unsupported or empty value';
  end if;
  v_protected := (p_environment='production');
  if v_protected and (p_allow_delete or 'delete'=any(p_allowed_operations)) then
    raise exception 'Production Worker registration cannot allow deletion';
  end if;
  if p_allow_delete and p_environment <> 'test' then raise exception 'Only explicitly classified test Workers can be registered with deletion permission'; end if;
  if p_allow_delete is distinct from ('delete'=any(p_allowed_operations)) then
    raise exception 'allow_delete must match the delete operation in the allow-list';
  end if;
  if p_environment='production' and 'update_metadata'=any(p_allowed_operations) then
    raise exception 'Production Worker metadata changes are blocked by default';
  end if;
  if exists(select 1 from private_cloudflare.worker_admin_allowlist where worker_name=p_worker_name and deleted_at is null) then
    raise exception 'Worker is already registered in the management allow-list';
  end if;

  v_list:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers',null);
  if coalesce((v_list->>'status')::int,0)<>200 then raise exception 'Could not verify Cloudflare Workers inventory'; end if;
  v_list_body:=(v_list->>'body')::jsonb;
  select x into v_item from jsonb_array_elements(coalesce(v_list_body->'result','[]'::jsonb)) x
    where x->>'name'=p_worker_name;
  if v_item is null then raise exception 'Worker name does not exist in the Cloudflare account'; end if;
  v_worker_id:=v_item->>'id';
  if v_worker_id is null or v_worker_id !~ '^[a-f0-9]{32}$' then raise exception 'Cloudflare Worker ID is missing or invalid'; end if;

  v_detail:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_worker_id,null);
  if coalesce((v_detail->>'status')::int,0)<>200 then raise exception 'Could not read Worker details; registration blocked'; end if;
  v_detail_body:=(v_detail->>'body')::jsonb;
  if coalesce((v_detail_body->>'success')::boolean,false) is not true
     or v_detail_body->'result'->>'name'<>p_worker_name then raise exception 'Cloudflare Worker identity did not match'; end if;
  v_refs:=v_detail_body->'result'->'references';
  if v_refs is null or jsonb_typeof(v_refs)<>'object' then raise exception 'Worker references could not be verified'; end if;
  for v_ref in select key,value from jsonb_each(v_refs) loop
    if v_ref.value is not null and v_ref.value not in ('null'::jsonb,'[]'::jsonb,'{}'::jsonb,'false'::jsonb) then
      v_support_upload:=false;
    end if;
  end loop;

  v_versions:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_worker_id||'/versions',null);
  v_deployments:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/scripts/'||p_worker_name||'/deployments',null);
  if coalesce((v_versions->>'status')::int,0)<>200 or coalesce((v_deployments->>'status')::int,0)<>200 then
    raise exception 'Could not verify the complete Worker version and deployment history';
  end if;
  v_versions_body:=(v_versions->>'body')::jsonb;
  v_deployments_body:=(v_deployments->>'body')::jsonb;
  if coalesce((v_versions_body->>'success')::boolean,false) is not true
     or coalesce((v_deployments_body->>'success')::boolean,false) is not true then
    raise exception 'Cloudflare did not confirm version/deployment inventory';
  end if;

  if jsonb_typeof(v_versions_body->'result')='array' then v_version_count:=jsonb_array_length(v_versions_body->'result'); end if;
  if v_version_count=0 then
    v_support_upload:=true;
    for v_ref in select key,value from jsonb_each(v_refs) loop
      if v_ref.value is not null and v_ref.value not in ('null'::jsonb,'[]'::jsonb,'{}'::jsonb,'false'::jsonb) then
        v_support_upload:=false;
      end if;
    end loop;
  else
    v_settings:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/scripts/'||p_worker_name||'/settings',null);
    if coalesce((v_settings->>'status')::int,0)=200 then
      v_settings_body:=(v_settings->>'body')::jsonb;
      v_support_upload:=coalesce((v_settings_body->>'success')::boolean,false)
        and coalesce(jsonb_array_length(v_settings_body->'result'->'bindings'),0)=0
        and (v_settings_body->'result'->'assets' is null or v_settings_body->'result'->'assets'='null'::jsonb)
        and not exists (select 1 from jsonb_each(v_refs) e where e.value is not null and e.value not in ('null'::jsonb,'[]'::jsonb,'{}'::jsonb,'false'::jsonb));
    end if;
  end if;

  insert into private_cloudflare.worker_admin_allowlist(
    worker_name,worker_id,environment,allowed_operations,production_protected,allow_delete,supports_simple_module_upload
  ) values (
    p_worker_name,v_worker_id,p_environment,
    array(select distinct x from unnest(p_allowed_operations||array['inspect']::text[]) x),
    v_protected,p_allow_delete,v_support_upload
  );

  if jsonb_typeof(v_versions_body->'result')='array' then
    for v_v in select value from jsonb_array_elements(v_versions_body->'result') loop
      if coalesce(v_v->>'id','') ~* '^[0-9a-f-]{36}$' then
        v_id:=(v_v->>'id')::uuid;
        v_was_deployed:=exists(
          select 1 from jsonb_array_elements(coalesce(v_deployments_body->'result'->'deployments','[]'::jsonb)) d,
               jsonb_array_elements(coalesce(d->'versions','[]'::jsonb)) dv
          where dv->>'version_id'=v_id::text
        );
        v_active:=exists(
          select 1 from jsonb_array_elements(coalesce(v_deployments_body->'result'->'deployments'->0->'versions','[]'::jsonb)) cv
          where cv->>'version_id'=v_id::text
        );
        insert into private_cloudflare.worker_admin_versions(
          worker_name,version_id,version_number,origin,was_deployed,is_currently_deployed,created_on,annotations
        ) values (
          p_worker_name,v_id,nullif(v_v->>'number','')::integer,'cloudflare',
          v_was_deployed,v_active,nullif(v_v->>'created_on','')::timestamptz,coalesce(v_v->'annotations','{}'::jsonb)
        ) on conflict(worker_name,version_id) do update set
          was_deployed=excluded.was_deployed,is_currently_deployed=excluded.is_currently_deployed,
          version_number=excluded.version_number,created_on=excluded.created_on,annotations=excluded.annotations;
      end if;
    end loop;
  end if;

  select array_agg(version_id) into v_current from private_cloudflare.worker_admin_versions
   where worker_name=p_worker_name and is_currently_deployed;
  update private_cloudflare.worker_admin_allowlist
    set active_version_ids=coalesce(v_current,array[]::uuid[]),last_reconciled_at=now()
    where worker_name=p_worker_name;

  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,http_status,api_success,result_summary)
  values(p_worker_name,v_worker_id,'register_allowlist',200,true,
    jsonb_build_object('environment',p_environment,'production_protected',v_protected,
      'allowed_operations',p_allowed_operations,'upload_supported',v_support_upload,'version_count',v_version_count));

  return jsonb_build_object('ok',true,'worker_name',p_worker_name,'worker_id',v_worker_id,
    'environment',p_environment,'production_protected',v_protected,'allowed_operations',p_allowed_operations,
    'allow_delete',p_allow_delete,'simple_module_upload_supported',v_support_upload,
    'known_versions',v_version_count,'active_version_ids',coalesce(v_current,array[]::uuid[]));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_list()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
  select coalesce(jsonb_agg(jsonb_build_object(
    'worker_name',a.worker_name,'worker_id',a.worker_id,'environment',a.environment,
    'enabled',a.enabled,'allowed_operations',a.allowed_operations,
    'production_protected',a.production_protected,'allow_delete',a.allow_delete,
    'simple_module_upload_supported',a.supports_simple_module_upload,
    'active_version_ids',a.active_version_ids,'last_reconciled_at',a.last_reconciled_at
  ) order by a.environment,a.worker_name),'[]'::jsonb)
  from private_cloudflare.worker_admin_allowlist a
  where a.deleted_at is null;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_refresh_versions(p_worker_name text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare
  v_target private_cloudflare.worker_admin_allowlist%rowtype;
  v_versions jsonb; v_v jsonb; v_deployments jsonb; v_id uuid; v_was boolean; v_active boolean;
  v_active_ids uuid[];
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist
   where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if not ('inspect'=any(v_target.allowed_operations)) then raise exception 'Inspection is not allowed for this Worker'; end if;

  v_versions:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id||'/versions',null);
  v_deployments:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/scripts/'||p_worker_name||'/deployments',null);
  if coalesce((v_versions->>'status')::int,0)<>200 or coalesce((v_deployments->>'status')::int,0)<>200 then
    raise exception 'Version/deployment refresh failed; local state left unchanged';
  end if;
  if coalesce(((v_versions->>'body')::jsonb->>'success')::boolean,false) is not true
     or coalesce(((v_deployments->>'body')::jsonb->>'success')::boolean,false) is not true then
    raise exception 'Cloudflare API did not confirm version/deployment inventory';
  end if;

  update private_cloudflare.worker_admin_versions set is_currently_deployed=false where worker_name=p_worker_name;
  for v_v in select value from jsonb_array_elements(coalesce((v_versions->>'body')::jsonb->'result','[]'::jsonb)) loop
    if coalesce(v_v->>'id','') ~* '^[0-9a-f-]{36}$' then
      v_id:=(v_v->>'id')::uuid;
      v_was:=exists(
        select 1 from jsonb_array_elements(coalesce((v_deployments->>'body')::jsonb->'result'->'deployments','[]'::jsonb)) d,
             jsonb_array_elements(coalesce(d->'versions','[]'::jsonb)) dv
        where dv->>'version_id'=v_id::text
      );
      v_active:=exists(
        select 1 from jsonb_array_elements(coalesce((v_deployments->>'body')::jsonb->'result'->'deployments'->0->'versions','[]'::jsonb)) cv
        where cv->>'version_id'=v_id::text
      );
      insert into private_cloudflare.worker_admin_versions(
        worker_name,version_id,version_number,origin,was_deployed,is_currently_deployed,created_on,annotations
      ) values (
        p_worker_name,v_id,nullif(v_v->>'number','')::integer,'cloudflare',v_was,v_active,
        nullif(v_v->>'created_on','')::timestamptz,coalesce(v_v->'annotations','{}'::jsonb)
      ) on conflict(worker_name,version_id) do update set
        was_deployed=private_cloudflare.worker_admin_versions.was_deployed or excluded.was_deployed,
        is_currently_deployed=excluded.is_currently_deployed,
        version_number=excluded.version_number,created_on=excluded.created_on,annotations=excluded.annotations;
    end if;
  end loop;

  select array_agg(version_id) into v_active_ids from private_cloudflare.worker_admin_versions
    where worker_name=p_worker_name and is_currently_deployed;
  update private_cloudflare.worker_admin_allowlist
     set active_version_ids=coalesce(v_active_ids,array[]::uuid[]),last_reconciled_at=now(),updated_at=now()
   where worker_name=p_worker_name;

  return jsonb_build_object('ok',true,'worker_name',p_worker_name,
    'active_version_ids',coalesce(v_active_ids,array[]::uuid[]),
    'tracked_versions',(select count(*) from private_cloudflare.worker_admin_versions where worker_name=p_worker_name));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_update_tags(p_worker_name text, p_tags text[], p_confirmation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare v_target private_cloudflare.worker_admin_allowlist%rowtype; v_r jsonb; v_b jsonb; v_ok boolean;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist
   where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if not ('update_metadata'=any(v_target.allowed_operations)) or v_target.production_protected then
    raise exception 'Metadata update is blocked by the Worker policy';
  end if;
  if p_confirmation is distinct from 'UPDATE METADATA '||p_worker_name then
    raise exception 'Exact metadata update confirmation is required';
  end if;
  if p_tags is null or cardinality(p_tags)>20 or exists(select 1 from unnest(p_tags) t where length(t)>100 or t !~ '^[A-Za-z0-9 _.:/-]+$') then
    raise exception 'Tags must contain at most 20 safe values, each no longer than 100 characters';
  end if;

  v_r:=private_cloudflare._worker_admin_http('PATCH',
    '/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id,
    jsonb_build_object('tags',to_jsonb(p_tags)));
  v_b:=v_r->'body'; v_ok:=coalesce((v_b->>'success')::boolean,false) and (v_r->>'status')::int between 200 and 299;
  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,http_status,api_success,result_summary)
  values(p_worker_name,v_target.worker_id,'update_metadata_tags',(v_r->>'status')::int,v_ok,
    jsonb_build_object('tag_count',cardinality(p_tags),'errors',coalesce(v_b->'errors','[]'::jsonb)));
  return jsonb_build_object('ok',v_ok,'worker_name',p_worker_name,'http_status',v_r->>'status',
    'errors',coalesce(v_b->'errors','[]'::jsonb));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_upload_module_version(p_worker_name text, p_module_js text, p_message text, p_confirmation text, p_compatibility_date date DEFAULT CURRENT_DATE)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare
  v_target private_cloudflare.worker_admin_allowlist%rowtype;
  v_body jsonb; v_r jsonb; v_b jsonb; v_id uuid; v_ok boolean; v_required text;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist
   where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if not ('upload_version'=any(v_target.allowed_operations)) then raise exception 'Version upload is not allowed for this Worker'; end if;
  if not v_target.supports_simple_module_upload then
    raise exception 'This Worker has bindings/assets or unverified settings; generic single-module upload is disabled to avoid dropping dependencies';
  end if;
  v_required:=case when v_target.production_protected
    then 'APPROVE PRODUCTION VERSION UPLOAD '||p_worker_name
    else 'UPLOAD VERSION '||p_worker_name end;
  if p_confirmation is distinct from v_required then raise exception 'Exact version upload confirmation is required'; end if;
  if p_module_js is null or length(p_module_js)=0 or octet_length(p_module_js)>200000 then
    raise exception 'Module source must be between 1 and 200000 bytes';
  end if;
  if p_message is null or length(p_message)>1000 then raise exception 'Version message is required and must be at most 1000 characters'; end if;
  if p_compatibility_date<date '2024-01-01' or p_compatibility_date>current_date then raise exception 'Compatibility date is outside the accepted range'; end if;

  v_body:=jsonb_build_object(
    'main_module','index.js',
    'compatibility_date',p_compatibility_date::text,
    'annotations',jsonb_build_object('workers/message',p_message,'workers/triggered_by','supabase-worker-admin-bridge'),
    'modules',jsonb_build_array(jsonb_build_object(
      'name','index.js','content_type','application/javascript+module',
      'content_base64',encode(convert_to(p_module_js,'UTF8'),'base64')
    ))
  );
  v_r:=private_cloudflare._worker_admin_http('POST',
    '/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id||'/versions?deploy=false',
    v_body);
  v_b:=v_r->'body';
  v_ok:=coalesce((v_b->>'success')::boolean,false)
        and coalesce((v_b->'result'->>'id'),'') ~* '^[0-9a-f-]{36}$';
  if v_ok then
    v_id:=(v_b->'result'->>'id')::uuid;
    insert into private_cloudflare.worker_admin_versions(worker_name,version_id,origin,was_deployed,is_currently_deployed,created_on,annotations)
    values(p_worker_name,v_id,'bridge',false,false,
      nullif(v_b->'result'->>'created_on','')::timestamptz,
      jsonb_build_object('workers/message',p_message))
    on conflict(worker_name,version_id) do nothing;
  end if;
  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,version_id,http_status,api_success,result_summary)
  values(p_worker_name,v_target.worker_id,'upload_version',v_id,(v_r->>'status')::int,v_ok,
    jsonb_build_object('message',p_message,'deployed',false,'errors',coalesce(v_b->'errors','[]'::jsonb)));
  return jsonb_build_object('ok',v_ok,'worker_name',p_worker_name,'version_id',v_id,
    'uploaded_without_deploy',true,'http_status',v_r->>'status','errors',coalesce(v_b->'errors','[]'::jsonb));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_deploy(p_worker_name text, p_version_id uuid, p_confirmation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare v_target private_cloudflare.worker_admin_allowlist%rowtype; v_version private_cloudflare.worker_admin_versions%rowtype;
 v_check jsonb; v_r jsonb; v_b jsonb; v_ok boolean; v_required text;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if not ('deploy'=any(v_target.allowed_operations)) then raise exception 'Deployment is not allowed for this Worker'; end if;
  select * into v_version from private_cloudflare.worker_admin_versions where worker_name=p_worker_name and version_id=p_version_id;
  if not found then raise exception 'Version is not registered in the bridge version inventory'; end if;
  if v_version.was_deployed or v_version.is_currently_deployed then
    raise exception 'This version is historical or active; use the rollback operation for a previously deployed version';
  end if;
  v_required:=case when v_target.production_protected
    then 'APPROVE PRODUCTION DEPLOY '||p_worker_name||' '||p_version_id::text
    else 'DEPLOY '||p_worker_name||' '||p_version_id::text end;
  if p_confirmation is distinct from v_required then raise exception 'Explicit deployment approval did not match'; end if;
  v_check:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id||'/versions/'||p_version_id::text,null);
  if coalesce((v_check->>'status')::int,0)<>200 or coalesce(((v_check->>'body')::jsonb->>'success')::boolean,false) is not true then
    raise exception 'Cloudflare no longer confirms the uploaded version; deployment blocked';
  end if;
  v_r:=private_cloudflare._worker_admin_http('POST',
    '/accounts/1171975142d29fc55425b752629bb8bd/workers/scripts/'||p_worker_name||'/deployments',
    jsonb_build_object('strategy','percentage','versions',jsonb_build_array(jsonb_build_object('version_id',p_version_id,'percentage',100)),
      'annotations',jsonb_build_object('workers/message','Deploy via Supabase bridge')));
  v_b:=v_r->'body'; v_ok:=coalesce((v_b->>'success')::boolean,false) and nullif(v_b->'result'->>'id','') is not null and (v_r->>'status')::int between 200 and 299;
  if v_ok then
    update private_cloudflare.worker_admin_versions set is_currently_deployed=false where worker_name=p_worker_name;
    update private_cloudflare.worker_admin_versions set was_deployed=true,is_currently_deployed=true,last_deployed_at=now()
      where worker_name=p_worker_name and version_id=p_version_id;
    update private_cloudflare.worker_admin_allowlist set active_version_ids=array[p_version_id],updated_at=now(),last_reconciled_at=now() where worker_name=p_worker_name;
  end if;
  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,version_id,http_status,api_success,result_summary)
  values(p_worker_name,v_target.worker_id,'deploy_version',p_version_id,(v_r->>'status')::int,v_ok,
    jsonb_build_object('deployment_id',v_b->'result'->>'id','environment',v_target.environment,'production_protected',v_target.production_protected,'errors',coalesce(v_b->'errors','[]'::jsonb)));
  return jsonb_build_object('ok',v_ok,'worker_name',p_worker_name,'version_id',p_version_id,
    'deployment_id',v_b->'result'->>'id','http_status',v_r->>'status','errors',coalesce(v_b->'errors','[]'::jsonb));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_rollback(p_worker_name text, p_version_id uuid, p_confirmation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare v_target private_cloudflare.worker_admin_allowlist%rowtype; v_version private_cloudflare.worker_admin_versions%rowtype;
 v_check jsonb; v_r jsonb; v_b jsonb; v_ok boolean; v_required text;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if not ('rollback'=any(v_target.allowed_operations)) then raise exception 'Rollback is not allowed for this Worker'; end if;
  select * into v_version from private_cloudflare.worker_admin_versions where worker_name=p_worker_name and version_id=p_version_id;
  if not found or not v_version.was_deployed or v_version.is_currently_deployed then
    raise exception 'Rollback target must be a known, previously deployed, non-active version';
  end if;
  v_required:=case when v_target.production_protected
    then 'APPROVE PRODUCTION ROLLBACK '||p_worker_name||' '||p_version_id::text
    else 'ROLLBACK '||p_worker_name||' '||p_version_id::text end;
  if p_confirmation is distinct from v_required then raise exception 'Explicit rollback approval did not match'; end if;
  v_check:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id||'/versions/'||p_version_id::text,null);
  if coalesce((v_check->>'status')::int,0)<>200 or coalesce(((v_check->>'body')::jsonb->>'success')::boolean,false) is not true then
    raise exception 'Cloudflare no longer confirms the rollback version; rollback blocked';
  end if;
  v_r:=private_cloudflare._worker_admin_http('POST',
    '/accounts/1171975142d29fc55425b752629bb8bd/workers/scripts/'||p_worker_name||'/deployments',
    jsonb_build_object('strategy','percentage','versions',jsonb_build_array(jsonb_build_object('version_id',p_version_id,'percentage',100)),
      'annotations',jsonb_build_object('workers/message','Rollback via Supabase bridge')));
  v_b:=v_r->'body'; v_ok:=coalesce((v_b->>'success')::boolean,false) and nullif(v_b->'result'->>'id','') is not null and (v_r->>'status')::int between 200 and 299;
  if v_ok then
    update private_cloudflare.worker_admin_versions set is_currently_deployed=false where worker_name=p_worker_name;
    update private_cloudflare.worker_admin_versions set is_currently_deployed=true,last_deployed_at=now()
      where worker_name=p_worker_name and version_id=p_version_id;
    update private_cloudflare.worker_admin_allowlist set active_version_ids=array[p_version_id],updated_at=now(),last_reconciled_at=now() where worker_name=p_worker_name;
  end if;
  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,version_id,http_status,api_success,result_summary)
  values(p_worker_name,v_target.worker_id,'rollback_version',p_version_id,(v_r->>'status')::int,v_ok,
    jsonb_build_object('deployment_id',v_b->'result'->>'id','environment',v_target.environment,'production_protected',v_target.production_protected,'force_used',false,'errors',coalesce(v_b->'errors','[]'::jsonb)));
  return jsonb_build_object('ok',v_ok,'worker_name',p_worker_name,'version_id',p_version_id,
    'deployment_id',v_b->'result'->>'id','http_status',v_r->>'status','force_used',false,'errors',coalesce(v_b->'errors','[]'::jsonb));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_delete(p_worker_name text, p_confirmation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare v_target private_cloudflare.worker_admin_allowlist%rowtype; v_detail jsonb; v_b jsonb; v_refs jsonb; v_ref record;
 v_r jsonb; v_rb jsonb; v_ok boolean;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if v_target.production_protected or v_target.environment <> 'test' then raise exception 'Only explicitly allowlisted test Workers can be deleted'; end if;
  if not v_target.allow_delete or not ('delete'=any(v_target.allowed_operations)) then raise exception 'Deletion is not allowed by the Worker allow-list'; end if;
  if p_confirmation is distinct from 'DELETE '||p_worker_name||' '||v_target.worker_id then raise exception 'Exact Worker deletion confirmation is required'; end if;

  v_detail:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id,null);
  if coalesce((v_detail->>'status')::int,0)<>200 then raise exception 'Worker could not be re-read; deletion blocked'; end if;
  v_b:=(v_detail->>'body')::jsonb;
  if coalesce((v_b->>'success')::boolean,false) is not true or v_b->'result'->>'name'<>p_worker_name then raise exception 'Worker identity verification failed'; end if;
  v_refs:=v_b->'result'->'references';
  if v_refs is null or jsonb_typeof(v_refs)<>'object' then raise exception 'Worker references are not inspectable; deletion blocked'; end if;
  for v_ref in select key,value from jsonb_each(v_refs) loop
    if v_ref.value is not null and v_ref.value not in ('null'::jsonb,'[]'::jsonb,'{}'::jsonb,'false'::jsonb) then
      raise exception 'Worker deletion blocked due to non-empty reference group %',v_ref.key;
    end if;
  end loop;
  if coalesce((v_b->'result'->'subdomain'->>'enabled')::boolean,true) then raise exception 'Worker workers.dev subdomain must be disabled before deletion'; end if;

  v_r:=private_cloudflare._worker_admin_http('DELETE',
    '/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id,null);
  v_b:=v_r->'body'; v_ok:=coalesce((v_b->>'success')::boolean,false) and (v_r->>'status')::int between 200 and 299;
  if v_ok then
    v_detail:=private_cloudflare.request('GET','/accounts/1171975142d29fc55425b752629bb8bd/workers/workers/'||v_target.worker_id,null);
    if coalesce((v_detail->>'status')::int,0)=404 then
      update private_cloudflare.worker_admin_allowlist set enabled=false,deleted_at=now(),active_version_ids=array[]::uuid[],updated_at=now() where worker_name=p_worker_name;
    else
      v_ok:=false;
    end if;
  end if;
  insert into private_cloudflare.worker_admin_audit(worker_name,worker_id,operation,http_status,api_success,result_summary)
  values(p_worker_name,v_target.worker_id,'delete_worker',(v_r->>'status')::int,v_ok,
    jsonb_build_object('verification_status',v_detail->>'status','errors',coalesce(v_b->'errors','[]'::jsonb)));
  return jsonb_build_object('ok',v_ok,'worker_name',p_worker_name,'http_status',v_r->>'status',
    'verification_status',v_detail->>'status','errors',coalesce(v_b->'errors','[]'::jsonb));
end;
$function$
;

CREATE OR REPLACE FUNCTION private_cloudflare.worker_admin_set_policy(p_worker_name text, p_environment text, p_allowed_operations text[], p_allow_delete boolean, p_confirmation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'private_cloudflare'
AS $function$
declare v_target private_cloudflare.worker_admin_allowlist%rowtype; v_protected boolean; v_required text;
begin
  select * into v_target from private_cloudflare.worker_admin_allowlist
   where worker_name=p_worker_name and enabled and deleted_at is null;
  if not found then raise exception 'Worker is not in the active allow-list'; end if;
  if p_environment not in ('production','staging','development','test') then raise exception 'Invalid Worker environment'; end if;
  if p_allowed_operations is null or cardinality(p_allowed_operations)=0
     or not (p_allowed_operations <@ array['inspect','update_metadata','upload_version','deploy','rollback','delete']::text[]) then
    raise exception 'Invalid operations allow-list';
  end if;
  v_protected:=(p_environment='production');
  if v_protected and (p_allow_delete or 'delete'=any(p_allowed_operations) or 'update_metadata'=any(p_allowed_operations)) then
    raise exception 'Production policy cannot enable deletion or metadata mutation';
  end if;
  if p_allow_delete is distinct from ('delete'=any(p_allowed_operations)) then raise exception 'allow_delete must match delete in the operation list'; end if;
  v_required:=case
    when v_target.production_protected and not v_protected
      then 'DEMOTE PRODUCTION PROTECTION '||p_worker_name||' TO '||p_environment
    else 'SET POLICY '||p_worker_name||' '||p_environment end;
  if p_confirmation is distinct from v_required then raise exception 'Exact policy confirmation is required'; end if;
  update private_cloudflare.worker_admin_allowlist
    set environment=p_environment,production_protected=v_protected,
        allowed_operations=array(select distinct x from unnest(p_allowed_operations||array['inspect']::text[]) x),
        allow_delete=p_allow_delete,updated_at=now()
   where worker_name=p_worker_name;
  return jsonb_build_object('ok',true,'worker_name',p_worker_name,'environment',p_environment,
    'production_protected',v_protected,'allowed_operations',p_allowed_operations,'allow_delete',p_allow_delete);
end;
$function$
;

drop trigger if exists worker_admin_audit_append_only on private_cloudflare.worker_admin_audit;
create trigger worker_admin_audit_append_only
before update or delete on private_cloudflare.worker_admin_audit
for each row execute function private_cloudflare.worker_admin_prevent_audit_mutation();;

comment on table private_cloudflare.worker_admin_allowlist is 'Explicit per-Worker allow-list; production protected by default; deletion restricted to test Workers.';
comment on table private_cloudflare.worker_admin_versions is 'Version history for new deployment candidates and previously deployed rollback targets.';
comment on table private_cloudflare.worker_admin_audit is 'Append-only operational audit metadata; no credentials or Worker source code stored.';;

revoke all on function private_cloudflare._worker_admin_http(text,text,jsonb) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.request(text,text,jsonb) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_delete(text,text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_deploy(text,uuid,text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_list() from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_prevent_audit_mutation() from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_refresh_versions(text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_register(text,text,text[],boolean) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_rollback(text,uuid,text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_set_policy(text,text,text[],boolean,text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_update_tags(text,text[],text) from public,anon,authenticated,service_role;

revoke all on function private_cloudflare.worker_admin_upload_module_version(text,text,text,text,date) from public,anon,authenticated,service_role;