# Local Setup

BATONX runs locally only — there is no hosted or production deployment.

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL, running locally with a database created for the project
- (Optional) an Anthropic API key, if you want AI-backed generation to actually run — see below

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set at least `DATABASE_URL` to point at your local PostgreSQL instance. Then:

```bash
python manage.py migrate
python manage.py runserver localhost:8000
```

### Environment variables (`backend/.env`)

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django's cryptographic signing key — use a real, private value outside local dev. |
| `DJANGO_DEBUG` | Django debug mode. `True` for local development only. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `CORS_ALLOWED_ORIGINS` | Frontend origin(s) allowed to call the API. |
| `CSRF_TRUSTED_ORIGINS` | Origin(s) trusted for CSRF-protected requests. |
| `ANTHROPIC_API_KEY` | Server-side only, never exposed to the browser. Optional — without it, AI-backed generation steps show an honest "AI isn't configured" state instead of failing. |
| `VYRA_MODEL` | Which Anthropic model to use for generation. (Retained internal name from an earlier product name; functionally unrelated to the current "BATONX" branding.) |
| `VYRA_AI_TIMEOUT_SECONDS` | Timeout for AI provider calls. |

Never commit `backend/.env` — it's already excluded via `.gitignore`; only `backend/.env.example` (placeholders only) is tracked.

## Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev -- -p 3010 -H localhost
```

### Environment variables (`frontend/.env.local`)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the backend API. The only variable read by the browser — no secret ever belongs here. |

## Canonical local ports

- **Frontend:** http://localhost:3010
- **Backend:** http://localhost:8000

Use `localhost` consistently for both — mixing a `127.0.0.1` frontend with a `localhost` backend (or vice versa) breaks session/CSRF cookies, since the browser treats them as different origins.

## Running both together

Start the backend and frontend in two terminals, in either order:

```bash
# terminal 1
cd backend && source .venv/bin/activate && python manage.py runserver localhost:8000

# terminal 2
cd frontend && npm run dev -- -p 3010 -H localhost
```

Then open http://localhost:3010.

## A Next.js caveat worth knowing

Do not run `next dev` and `next build` against the same `.next` directory at the same time — a production build's cache/manifest is incompatible with a live dev server's, and can corrupt it (symptom: pages render but CSS silently stops applying). If you need to validate a production build while developing:

```bash
# stop the dev server first, then:
cd frontend
npm run build
rm -rf .next
npm run dev -- -p 3010 -H localhost
```

## Backend validation

```bash
cd backend
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

## Frontend validation

```bash
cd frontend
npx tsc --noEmit
npx eslint src --max-warnings=0
```
