# Development Approach

BATONX was built using a structured, AI-assisted software engineering workflow — the same underlying principle the product itself is built around, applied to building it: **a human leads, an orchestration process structures the work, and an AI agent executes against clear direction.**

## Workflow

1. **Requirements** — each phase of work started from an explicit, written specification: what to build, what not to touch, and what "done" meant for that phase.
2. **Architecture** — system design, domain modeling, and API/data-model decisions were made deliberately, before implementation, and captured as part of the specification.
3. **Task decomposition** — work was broken into scoped, reviewable phases (a single Journey stage, a single subsystem) rather than one undifferentiated build.
4. **Coding-agent implementation** — a coding agent implemented each phase against that specification, accelerating the mechanical work of writing and wiring code.
5. **Human review** — every phase's output was reviewed against the original intent before being accepted, including reading generated code, not just its behavior.
6. **Testing** — new domain rules shipped with corresponding automated tests; the full backend suite had to stay green.
7. **Debugging** — issues (including real ones found via live QA, not just written specs) were root-caused before being fixed — see, for example, the Next.js dev/build cache interaction documented in [`TESTING.md`](TESTING.md), diagnosed methodically rather than patched around.
8. **Regression verification** — `manage.py test`, `manage.py check`, `makemigrations --check`, TypeScript, ESLint, and a production build were run at the end of each phase, every time.

## What this means honestly

- **Not every line was manually typed** — coding agents accelerated implementation throughout.
- **The product does not build itself** — BATONX's own AI usage is scoped to producing a reviewable draft (see [`AI_ARCHITECTURE.md`](AI_ARCHITECTURE.md)); it does not autonomously design or ship its own features, and neither did the process used to build it. Every phase's direction, review, and acceptance was human-driven.
- **AI accelerates implementation; a human owns the engineering decisions** — requirements, architecture, domain modeling, security decisions, and what actually gets merged were never delegated.

This is described here as **AI-assisted software engineering**, not as an autonomous or "vibe-coded" build — the distinction matters, and it's the same distinction BATONX itself exists to enforce for its users: AI proposes, a human decides, and the decision is what persists.
