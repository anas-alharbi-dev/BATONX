# Security

This describes the authentication and authorization model actually implemented in BATONX today. It is not a security certification, a penetration-test report, or a claim of production hardening.

## Authentication

- Session-based authentication via Django's built-in session framework (`common/auth.py`), not a bearer token stored in browser local storage.
- A dedicated authentication class forces a `401 Unauthorized` for an unauthenticated request rather than Django REST Framework's default `403`, so the frontend can distinguish "not signed in" from "signed in but not allowed."
- Signup, login, logout, and "who am I" are the only authentication endpoints; there is no password-reset flow, OAuth, or SSO implemented yet.

## CSRF

- Django's CSRF protection is enforced on every unsafe (non-GET) request.
- The frontend and backend must run on trusted, explicitly configured origins (`CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` in `backend/.env`) — there is no wildcard origin in the default configuration.

## Ownership & isolation

- Every `Project` has a real `owner` foreign key to a Django `User`.
- Every request that touches a project resolves through one shared function that looks the project up scoped to the authenticated user — a single authorization chokepoint, not a separate ownership check per view.
- Every nested resource (tasks, datasets, metrics, queries, proposals, conversations, …) is looked up scoped to its parent project (`Model.objects.get(id=x, project=project)`) rather than by a bare primary key, so a valid id belonging to someone else's project can never be reached through a different project's URL.
- Requesting a project you don't own returns a plain `404 Not Found` — the same response as a project that doesn't exist at all. It never discloses that a project exists under a different account.

## What is not implemented

- No formal security audit or third-party penetration test
- No organization/team-level permissions — ownership is single-user only
- No rate limiting or brute-force login protection
- No password-reset or account-recovery flow
- No dependency/vulnerability scanning pipeline configured in this repository

## Local development defaults

`backend/.env.example` ships intentionally insecure local-development defaults (`DJANGO_DEBUG=True`, a placeholder `DJANGO_SECRET_KEY`). These are appropriate for running the product on `localhost` only and **must never be used as-is** for any environment reachable outside your own machine.

## Responsible disclosure

This is a personal/portfolio project, not a maintained product with a formal disclosure process. Please do not publish exploitable vulnerabilities, secrets, or private data in public GitHub issues — if you find something concerning, contact the author privately first.
