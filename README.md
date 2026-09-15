# Authentication and private user data

The application uses Supabase Auth for Google sign-in and Supabase Postgres for
private chat and exam data. Apply `supabase/migrations/0001_user_accounts.sql`
to the selected Supabase project, enable the Google provider, and register
`http://localhost:3000/auth/callback` plus the production callback URL in the
Supabase redirect allowlist.

## Local Supabase development

The portable Supabase CLI configuration and migrations are committed in
`supabase/`; generated state, signing material, and local env files are not.

1. Run `npx supabase start` from the repository root. This project uses ports
   `54331` (API), `54332` (database), and `54333` (Studio) to avoid colliding
   with the local workout tracker.
2. Copy `frontend/.env.example` to `frontend/.env.local`.
3. Copy `.local.env.example` to `.local.env`.
4. Run `npx supabase status`, then copy its API URL, publishable key, anon key,
   and secret/service key into the appropriate local env files.
5. Run `npx supabase db reset` to apply the migration locally.

For local Google login, set the Google client ID and secret in `.local.env`,
and register the local Supabase callback URL with Google. Google sign-in is
enabled in `supabase/config.toml`.

## Run locally

Prerequisites: Docker, Node.js, `uv`, and the Supabase CLI (`npx supabase` will
download it when needed). Keep all keys in ignored local env files; do not add
them to source control.

```bash
# One-time setup
uv sync
cd frontend && npm install && cd ..
cp frontend/.env.example frontend/.env.local
cp .local.env.example .local.env

# Start local Supabase with the Google values you added to .local.env.
set -a; source .local.env; set +a
npx supabase start
npx supabase db reset

# Copy API_URL, PUBLISHABLE_KEY, ANON_KEY, and SERVICE_ROLE_KEY from this output
# into frontend/.env.local and .local.env as documented above.
npx supabase status

# Terminal 1: API
set -a; source .local.env; set +a
EXAM_BUILDER_ENABLED=true uv run uvicorn server:app --app-dir src --reload

# Terminal 2: UI
cd frontend
npm run dev
```

Open `http://localhost:3000`, choose **Continue with Google**, and sign in.
To shut down the local database stack later, run `npx supabase stop` from the
repository root.

For a hosted deployment, set these locally (never commit their values):

```text
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

`NEXT_PUBLIC_SUPABASE_ANON_KEY` remains accepted temporarily for existing
deployments, but `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` is the preferred name.
`SUPABASE_SERVICE_ROLE_KEY` belongs only to the backend. Do not expose it to
the frontend or place it in a `NEXT_PUBLIC_` variable.
