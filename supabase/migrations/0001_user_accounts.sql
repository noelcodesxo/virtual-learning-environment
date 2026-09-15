create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now()
);

create table public.chat_threads (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.chat_messages (
  id bigint generated always as identity primary key,
  thread_id uuid not null references public.chat_threads(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  sources jsonb,
  created_at timestamptz not null default now()
);

create table public.exams (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  book text not null, chapter text not null, generated_from text not null,
  description text, requested_question_count integer not null,
  answers jsonb, score integer, created_at timestamptz not null default now()
);

create table public.exam_questions (
  id uuid primary key, exam_id uuid not null references public.exams(id) on delete cascade,
  position integer not null, section text not null, question text not null, options jsonb not null,
  unique (exam_id, position)
);

create table public.exam_answer_keys (
  question_id uuid primary key references public.exam_questions(id) on delete cascade,
  correct_index integer not null check (correct_index between 0 and 3), why text not null
);

alter table public.profiles enable row level security;
alter table public.chat_threads enable row level security;
alter table public.chat_messages enable row level security;
alter table public.exams enable row level security;
alter table public.exam_questions enable row level security;
alter table public.exam_answer_keys enable row level security;

create policy "users read own profile" on public.profiles for select using (id = auth.uid());
create policy "users read own threads" on public.chat_threads for select using (user_id = auth.uid());
create policy "users read own messages" on public.chat_messages for select using (user_id = auth.uid());
create policy "users read own exams" on public.exams for select using (user_id = auth.uid());
create policy "users read own questions" on public.exam_questions for select using (
  exists (select 1 from public.exams where exams.id = exam_questions.exam_id and exams.user_id = auth.uid())
);

create function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (new.id, new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'avatar_url');
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_user();
