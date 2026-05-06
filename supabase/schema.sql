create table if not exists public.push_subscriptions (
  endpoint text primary key,
  subscription jsonb not null,
  user_agent text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.notification_state (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default timezone('utc', now())
);

alter table public.push_subscriptions enable row level security;
alter table public.notification_state enable row level security;

grant usage on schema public to anon, authenticated, service_role;
grant insert, update on public.push_subscriptions to anon;
grant select, insert, update, delete on public.push_subscriptions to service_role;
grant select, insert, update, delete on public.notification_state to service_role;

drop policy if exists "anon can insert push subscriptions" on public.push_subscriptions;
create policy "anon can insert push subscriptions"
on public.push_subscriptions
for insert
to anon
with check (true);

drop policy if exists "anon can update push subscriptions" on public.push_subscriptions;
create policy "anon can update push subscriptions"
on public.push_subscriptions
for update
to anon
using (true)
with check (true);

drop policy if exists "service role manages notification state" on public.notification_state;
create policy "service role manages notification state"
on public.notification_state
for all
to service_role
using (true)
with check (true);

drop policy if exists "service role manages push subscriptions" on public.push_subscriptions;
create policy "service role manages push subscriptions"
on public.push_subscriptions
for all
to service_role
using (true)
with check (true);
