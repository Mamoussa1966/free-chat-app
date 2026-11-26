create table if not exists public.clerk_auth_pilot_records (
  record_id uuid primary key default gen_random_uuid(),
  owner_subject text not null
    check (char_length(owner_subject) between 1 and 255),
  record_key text not null
    check (char_length(record_key) between 1 and 128),
  record_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint clerk_auth_pilot_records_owner_key_unique
    unique (owner_subject, record_key)
);

comment on table public.clerk_auth_pilot_records is
  'Isolated Clerk Development authentication pilot; not used by production or canonical AI Council conversation storage.';

alter table public.clerk_auth_pilot_records enable row level security;

grant select, insert, update, delete
  on table public.clerk_auth_pilot_records
  to authenticated;

create policy clerk_auth_pilot_clerk_issuer_only
  on public.clerk_auth_pilot_records
  as restrictive
  for all
  to authenticated
  using (
    (select auth.jwt() ->> 'iss') =
    'https://dear-hermit-1240.clerk.accounts.dev'
  )
  with check (
    (select auth.jwt() ->> 'iss') =
    'https://dear-hermit-1240.clerk.accounts.dev'
  );

create policy clerk_auth_pilot_select_own
  on public.clerk_auth_pilot_records
  for select
  to authenticated
  using (
    owner_subject = (select auth.jwt() ->> 'sub')
  );

create policy clerk_auth_pilot_insert_own
  on public.clerk_auth_pilot_records
  for insert
  to authenticated
  with check (
    owner_subject = (select auth.jwt() ->> 'sub')
  );

create policy clerk_auth_pilot_update_own
  on public.clerk_auth_pilot_records
  for update
  to authenticated
  using (
    owner_subject = (select auth.jwt() ->> 'sub')
  )
  with check (
    owner_subject = (select auth.jwt() ->> 'sub')
  );

create policy clerk_auth_pilot_delete_own
  on public.clerk_auth_pilot_records
  for delete
  to authenticated
  using (
    owner_subject = (select auth.jwt() ->> 'sub')
  );
