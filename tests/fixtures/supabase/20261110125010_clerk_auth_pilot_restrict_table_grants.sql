-- Remove inherited/default PUBLIC and anon access from the Clerk pilot table.
-- The authenticated role retains only the explicitly intended CRUD grants.
revoke all privileges on table public.clerk_auth_pilot_records from public;
revoke all privileges on table public.clerk_auth_pilot_records from anon;
grant select, insert, update, delete
  on table public.clerk_auth_pilot_records
  to authenticated;
