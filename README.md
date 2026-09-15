# Authentication and private user data

The application uses Supabase Auth for Google sign-in and Supabase Postgres for
private chat and exam data. Apply `supabase/migrations/0001_user_accounts.sql`
to the selected Supabase project, enable the Google provider, and register
`http://localhost:3000/auth/callback` plus the production callback URL in the
Supabase redirect allowlist.

Set these locally (never commit their values):

```text
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

`SUPABASE_SERVICE_ROLE_KEY` belongs only to the backend. Do not expose it to
the frontend or place it in a `NEXT_PUBLIC_` variable.
