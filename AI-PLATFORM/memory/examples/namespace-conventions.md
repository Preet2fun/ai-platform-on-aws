# Example — Namespace Conventions (generic)

Namespaces are file-system-like hierarchical paths that organize and isolate long-term
memory records. Design them **before** enabling strategies. Guidance and placeholders
follow the AWS AgentCore Memory blogs (see `../reference/SOURCES.md`).

## What namespaces provide [1]
- **Organizational structure** — separate memory types (preferences, summaries, facts).
- **Access control** — govern which memories are accessible in which context.
- **Multi-tenant isolation** — segregate by org/user, e.g. `/org_id/user_id/preferences/`.
- **Focused retrieval** — query one namespace without scanning unrelated records.

## Dynamic placeholders [1]
Namespace templates support runtime placeholders resolved from the events being processed:
- `{actorId}` — the actor identifier (user, agent, project, or combination)
- `{sessionId}` — groups related events
- `{strategyId}` — the strategy identifier

This avoids hardcoding identifiers, e.g. `namespaceTemplate: ["/{actorId}/facts/"]`.

## Example patterns [1][2]
| Purpose | Namespace |
|---|---|
| A specific actor's preferences | `/<agent>/{actorId}/preferences/` |
| Shared knowledge accessible to many | `/<agent>/shared/knowledge/` |
| Per-session summaries | `/<agent>/{actorId}/{sessionId}/summary/` |
| Facts about an actor | `/<agent>/{actorId}/facts/` |
| Episodes (episodic strategy) | `/<agent>/{actorId}/episodes/{sessionId}/` |
| Reflections (episodic) | `/<agent>/{actorId}/reflections/` |

## Multi-tenant isolation
Put the isolation boundary outermost so per-boundary retrieval, export, and deletion stay
clean, e.g. `/org_id/user_id/preferences/`. [1] Structure namespaces to reflect the
application's hierarchy for precise isolation and efficient retrieval; use a per-user path
for individual memories and a shared path for team-wide information. [2]

## Rules
- **Reflection namespace must be a sub-path of the episode namespace** (episodic). [3]
- Don't mix agents/strategies in one namespace — keep types in distinct containers. [1]
- Combine namespaces with retrieval scope (`namespace` + `topK`) for focused queries. [1]

_Source: AWS AgentCore Memory blogs [1][2][3] in `../reference/SOURCES.md`. Rephrased for
compliance._
