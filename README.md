# Platform

Independent personal AI platform, currently in architecture design.

The management plane covers Skill registration, business capability registration, A2UI composition, and Skill Workflow composition. The product plane contains a digital employee frontend/backend and a separate business-independent Agent/Workflow Runtime.

PostgreSQL is the only relational persistence engine across development, integration tests and deployment. Multiple application instances must share durable state. A single host is an initial deployment choice, not a high-availability claim.

See `docs/workstreams.md` for ownership and delivery order. No application implementation or runtime readiness is claimed by this documentation baseline.
