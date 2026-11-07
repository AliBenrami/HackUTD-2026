create schema if not exists private;

revoke all on schema private from public;
revoke all on schema private from anon, authenticated;

create table public.courses (
  id text primary key,
  name text not null,
  location text not null,
  summary text not null
);

create table public.tee_sets (
  id text primary key,
  course_id text not null references public.courses (id) on delete cascade,
  name text not null,
  marker text not null,
  rating numeric(4, 1) not null,
  slope smallint not null,
  sort_order smallint not null,
  unique (course_id, name)
);

create index tee_sets_course_id_idx on public.tee_sets (course_id);

create table public.holes (
  tee_set_id text not null references public.tee_sets (id) on delete cascade,
  hole_number smallint not null check (hole_number between 1 and 18),
  par smallint not null check (par in (3, 4, 5)),
  yards integer not null check (yards > 0),
  handicap smallint not null check (handicap between 1 and 18),
  primary key (tee_set_id, hole_number)
);

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
);

create table public.preferences (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  units text not null default 'yards' check (units in ('yards', 'meters')),
  show_distance boolean not null default true,
  show_elevation boolean not null default true,
  show_score boolean not null default true,
  show_wind boolean not null default false,
  sync_scores boolean not null default false,
  device_name text not null default 'Horizon Visor',
  device_model text not null default 'GA-1',
  device_connected boolean not null default false,
  device_battery smallint,
  device_firmware text,
  last_sync_at timestamptz
);

create table public.recent_courses (
  user_id uuid not null references public.profiles (id) on delete cascade,
  course_id text not null references public.courses (id),
  selected_at timestamptz not null default now(),
  primary key (user_id, course_id)
);

create index recent_courses_course_id_idx on public.recent_courses (course_id);

create table public.rounds (
  id uuid primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  course_id text not null references public.courses (id),
  tee_set_id text not null references public.tee_sets (id),
  nine text not null check (nine in ('front', 'back', 'full')),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null check (status in ('active', 'completed')),
  current_hole smallint not null check (current_hole between 1 and 18),
  sample boolean not null default false
);

create index rounds_user_started_idx on public.rounds (user_id, started_at desc);
create index rounds_course_id_idx on public.rounds (course_id);
create index rounds_tee_set_id_idx on public.rounds (tee_set_id);
create unique index rounds_one_active_idx on public.rounds (user_id) where status = 'active';

create table public.hole_scores (
  round_id uuid not null references public.rounds (id) on delete cascade,
  hole_number smallint not null check (hole_number between 1 and 18),
  strokes smallint check (strokes is null or strokes > 0),
  putts smallint check (putts is null or putts >= 0),
  penalties smallint check (penalties is null or penalties >= 0),
  fairway_hit boolean,
  completed boolean not null default false,
  primary key (round_id, hole_number)
);

create table public.swing_videos (
  id uuid primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  club text not null,
  source text not null check (source in ('camera', 'import')),
  storage_path text not null unique,
  created_at timestamptz not null default now()
);

create index swing_videos_user_created_idx on public.swing_videos (user_id, created_at desc);

create table public.swings (
  id uuid primary key,
  video_id uuid not null references public.swing_videos (id) on delete cascade,
  position smallint not null check (position > 0),
  created_at timestamptz not null default now(),
  unique (video_id, position)
);

create index swings_video_id_idx on public.swings (video_id);

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(nullif(btrim(new.raw_user_meta_data ->> 'display_name'), ''), 'You')
  );
  insert into public.preferences (user_id)
  values (new.id);
  return new;
end;
$$;

revoke all on function private.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function private.handle_new_user();

alter table public.courses enable row level security;
alter table public.tee_sets enable row level security;
alter table public.holes enable row level security;
alter table public.profiles enable row level security;
alter table public.preferences enable row level security;
alter table public.recent_courses enable row level security;
alter table public.rounds enable row level security;
alter table public.hole_scores enable row level security;
alter table public.swing_videos enable row level security;
alter table public.swings enable row level security;

create policy courses_read on public.courses
  for select to authenticated
  using (true);

create policy tee_sets_read on public.tee_sets
  for select to authenticated
  using (true);

create policy holes_read on public.holes
  for select to authenticated
  using (true);

create policy profiles_select on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));

create policy profiles_update on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

create policy preferences_all on public.preferences
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy recent_courses_all on public.recent_courses
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy rounds_all on public.rounds
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy hole_scores_all on public.hole_scores
  for all to authenticated
  using (
    exists (
      select 1 from public.rounds
      where rounds.id = hole_scores.round_id
        and rounds.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.rounds
      where rounds.id = hole_scores.round_id
        and rounds.user_id = (select auth.uid())
    )
  );

create policy swing_videos_all on public.swing_videos
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy swings_all on public.swings
  for all to authenticated
  using (
    exists (
      select 1 from public.swing_videos
      where swing_videos.id = swings.video_id
        and swing_videos.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.swing_videos
      where swing_videos.id = swings.video_id
        and swing_videos.user_id = (select auth.uid())
    )
  );

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'swing-videos',
  'swing-videos',
  false,
  52428800,
  array['video/mp4', 'video/webm', 'video/quicktime']
);

create policy swing_video_objects_select on storage.objects
  for select to authenticated
  using (
    bucket_id = 'swing-videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy swing_video_objects_insert on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'swing-videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy swing_video_objects_update on storage.objects
  for update to authenticated
  using (
    bucket_id = 'swing-videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'swing-videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy swing_video_objects_delete on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'swing-videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );
