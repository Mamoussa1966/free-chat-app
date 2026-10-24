-- Restrict the optional project-level RLS event-trigger helper if it exists.
-- Some projects install this helper outside the repository's migrations.
-- It still enables RLS for newly created public tables; API roles do not need
-- permission to invoke the helper directly.
do $migration$
begin
    if to_regprocedure('public.rls_auto_enable()') is not null then
        execute 'revoke all privileges on function public.rls_auto_enable() from public, anon, authenticated, service_role';
    end if;
end
$migration$;
