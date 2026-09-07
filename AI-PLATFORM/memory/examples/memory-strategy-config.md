# Example — Memory Strategy Config (generic)

Generic, use-case-agnostic examples of creating a memory resource, defining strategies,
storing events, and retrieving records. API shapes follow the AWS AgentCore Memory blogs
(see `../reference/SOURCES.md`). Names/namespaces are placeholders. Verify against current
docs before running.

## 1. Create a memory resource (short-term only)
```python
import time, boto3
client = boto3.client("bedrock-agentcore")  # region as needed

resp = client.create_memory(
    name="ExampleMemory",
    description="Memory store for an agent",
    eventExpiryDuration=30,        # raw events retained 30 days (max 365)
    encryptionKeyArn="arn:aws:kms:<region>:<account>:key/<id>",  # optional CMK
)
memory_id = resp["memoryId"]       # returned on creation
```

## 2. Create a memory resource with long-term strategies
```python
strategies = [
    {"semanticMemoryStrategy": {
        "name": "semantic-facts",
        "namespaceTemplate": ["/{actorId}/facts/"]}},
    {"summaryMemoryStrategy": {
        "name": "conversation-summary",
        "namespaceTemplate": ["/{actorId}/{sessionId}/summary/"]}},
    {"userPreferenceMemoryStrategy": {
        "name": "user-preferences",
        "namespaceTemplate": ["/{actorId}/preferences/"]}},
]

resp = client.create_memory(
    name="ExampleMemory",
    description="Memory store with long-term strategies",
    eventExpiryDuration=30,
    memoryStrategies=strategies,
)
```
> Episodic strategy is configured similarly (with an episode namespace and a reflection
> namespace that is a sub-path of it). Confirm the exact key name for the episodic strategy
> against current docs.

## 3. Store a Conversational event (short-term; feeds extraction)
```python
client.create_event(
    memoryId=memory_id,
    actorId="actor-123",
    sessionId="session-789",
    eventTimestamp=int(time.time() * 1000),
    payload=[
        {"conversational": {"content": {"text": "..."}, "role": "USER"}},
        {"conversational": {"content": {"text": "..."}, "role": "ASSISTANT"}},
    ],
)
```

## 4. List recent raw events (short-term context)
```python
events = client.list_events(
    memoryId=memory_id,
    actorId="actor-123",
    sessionId="session-789",
    maxResults=10,
)
```

## 5. Retrieve long-term records (semantic search) — retrieve-before-act
```python
memories = client.retrieve_memory_records(
    memoryId=memory_id,
    namespace="/actor-123/preferences/",
    searchCriteria={"searchQuery": "<query>", "topK": 5},
)
# Hydrate the agent's context with these BEFORE it reasons.
```

## 6. Customization options
- **Built-in with overrides:** custom extraction/consolidation prompts + custom model
  selection (balance accuracy vs. latency), set as a strategy override at create time.
- **Self-managed:** run your own extraction/consolidation and ingest records via Batch
  APIs; AgentCore handles storage + retrieval.

---

### Notes
- STM stores events **synchronously**; long-term extraction/consolidation is
  **asynchronous** (~20–40s) — design for the delay; use STM for immediate recall.
- Only **Conversational** events feed long-term extraction; **blob** events (e.g.
  checkpoints) are excluded.
- Built-in strategies ignore PII by default.
- Namespace placeholders: `{actorId}`, `{sessionId}`, `{strategyId}`.

_Source: AWS AgentCore Memory blogs [1][2][3] in `../reference/SOURCES.md`. Rephrased for
compliance; verify API shapes against current documentation._
