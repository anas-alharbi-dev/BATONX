# Testing

## Backend — 563 automated tests

Run with Django's own test runner:

```bash
cd backend
python manage.py test
```

**Philosophy:** these tests exist primarily as regression protection for a product that grew across many incremental phases — every new capability shipped alongside tests for the domain rules it introduced, and the full suite has to stay green before any further change is considered done.

**What the suite covers:**

- **Software workflow** — Discovery through Delivery Readiness: generation, approval, editing, edit-locking once a downstream artifact exists, and regeneration.
- **Data workflow** — Brief through Delivery: dataset registration/profiling, quality resolution, transformation, metrics, queries, analysis, and dashboard readiness.
- **Authentication & ownership** — signup/login/logout, session behavior, and that a project (and everything nested under it) is reachable only by its owner.
- **Proposals** — creation, approval (including the real content mutation it triggers), rejection (verifying zero mutation), and the conflict path when an artifact is locked against further edits.
- **Stale-dependency propagation** — that approving or editing an upstream artifact correctly marks the real, specific downstream artifacts stale, across both Software and Data.
- **Progress & delivery-readiness computation** — that these are derived correctly from real task/artifact state, not approximated.

563 tests is a measure of regression coverage on a real, evolving codebase — not a claim that the product is bug-free.

## Frontend — validation, not an automated test suite

The frontend does not currently have an automated test suite (no Jest/Vitest/Playwright). It's validated instead with:

```bash
cd frontend
npx tsc --noEmit           # TypeScript, strict compilation
npx eslint src --max-warnings=0
npm run build              # production build must succeed
```

This is an honest gap, not a hidden one — automated frontend testing is a natural next investment, not something already in place.

## A practical Next.js caveat found during this project

Do not run `next dev` and `next build` against the same `.next` directory at the same time — a live dev server and a production build write incompatible cache/manifest formats into `.next`, which can corrupt the dev server's asset manifest (symptom: pages render but styling silently breaks). If you need to validate a production build while a dev server is running:

1. Stop the dev server.
2. Run `npm run build`.
3. Remove `.next` and restart the dev server cleanly (`rm -rf .next && npm run dev -- -p 3010 -H localhost`).

See [`LOCAL_SETUP.md`](LOCAL_SETUP.md) for the full local setup.
