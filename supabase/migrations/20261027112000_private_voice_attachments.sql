-- Private original voice attachments for authenticated AI Council conversations.
-- All Storage operations use the signed-in user's JWT; no service key is needed.
begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'council-voice-files',
    'council-voice-files',
    false,
    8388608,
    array['audio/wav', 'audio/x-wav', 'audio/webm', 'audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/aac']::text[]
)
on conflict (id) do update
set name = excluded.name,
    public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists council_voice_select_own on storage.objects;
create policy council_voice_select_own
on storage.objects for select to authenticated
using (
    bucket_id = 'council-voice-files'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop policy if exists council_voice_insert_own on storage.objects;
create policy council_voice_insert_own
on storage.objects for insert to authenticated
with check (
    bucket_id = 'council-voice-files'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);

-- Storage upsert requires SELECT + INSERT + UPDATE. Paths are immutable message IDs;
-- UPDATE is limited to the same authenticated user's own object folder.
drop policy if exists council_voice_update_own on storage.objects;
create policy council_voice_update_own
on storage.objects for update to authenticated
using (
    bucket_id = 'council-voice-files'
    and (storage.foldername(name))[1] = (select auth.uid())::text
)
with check (
    bucket_id = 'council-voice-files'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop policy if exists council_voice_delete_own on storage.objects;
create policy council_voice_delete_own
on storage.objects for delete to authenticated
using (
    bucket_id = 'council-voice-files'
    and (storage.foldername(name))[1] = (select auth.uid())::text
);

commit;
