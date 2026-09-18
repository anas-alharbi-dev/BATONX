# Software Journey

The real, end-to-end path a Software project follows in BATONX. Each stage's input, purpose, and output — the same order the Workspace's Journey rail follows, computed deterministically from real project state (never guessed from a chat transcript).

## Discovery

- **Input:** a raw idea, in the project creator's own words.
- **Purpose:** answer a small set of targeted questions that shape everything downstream — who it's for, what it must do, what it explicitly doesn't need to do.
- **Output:** structured discovery answers, stored as permanent project context for the Blueprint.

## Blueprint

- **Input:** the approved Discovery answers.
- **Purpose:** define the product itself — problem, solution, target users, roles, core/MVP/future features, functional requirements, business rules, user flows, and what's explicitly out of scope.
- **Output:** an approved Blueprint — the source of truth every later stage is built against.

## Business Logic

- **Input:** the approved Blueprint.
- **Purpose:** make the rules an implementer would otherwise have to invent explicit — permissions, validations, state transitions, and edge cases, each traceable back to a requirement. Skipped automatically when a project's Architecture doesn't need a distinct rules layer.
- **Output:** an approved Business Logic artifact, authoritative for Architecture and the Roadmap.

## Architecture

- **Input:** the approved Blueprint (and Business Logic, when present).
- **Purpose:** a pragmatic technical design — stack, components, API surface, a conceptual data model, integrations, security, deployment approach, and the key decisions, each with a stated rationale.
- **Output:** an approved Architecture — the input to the Roadmap, and what an execution agent is meant to build against.

## Roadmap

- **Input:** the approved Architecture.
- **Purpose:** break the work into phases and tasks with explicit dependencies, in an order that respects them.
- **Output:** an approved Roadmap — a real, dependency-ordered task graph, not a flat checklist.

## Tasks / Build

- **Input:** an approved Roadmap task, once its dependencies are complete.
- **Purpose:** generate a context-aware Build Prompt for that specific task — carrying the relevant Architecture, Business Logic, and requirement context an execution agent needs, without re-explaining the whole project.
- **Output:** a Build Prompt, ready to hand to Claude Code, Codex, Cursor, or any other execution agent.

## Review

- **Input:** a task marked ready for review.
- **Purpose:** generate a Review Prompt scoped to what that task was actually supposed to deliver, so review has a concrete standard rather than "does this look right."
- **Output:** a completed or reopened task, based on the human's review decision.

## Progress

- **Input:** the real state of every task across the Roadmap.
- **Purpose:** show what's done, in progress, in review, or blocked — computed from actual task status and dependency state, never a rough estimate.
- **Output:** a live progress view and the single deterministic "next action" the project should take.

## Delivery Readiness

- **Input:** the full project state — approvals, task completion, and outstanding review items.
- **Purpose:** a real checklist of automatic checks plus your own manual confirmations before calling a project delivery-ready.
- **Output:** an honest readiness status — never a rubber stamp.
