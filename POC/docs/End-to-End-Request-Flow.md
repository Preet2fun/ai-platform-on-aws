# Motadata MSP AI Assistant — End-to-End Request/Response Flow

> Based on live discovery of AWS account `001961766007`, region `us-east-1`.
> Diagrams are Mermaid — they render in GitHub, VS Code (with a Mermaid extension),
> and most Markdown viewers.

This document traces a user request from the browser all the way through the
supervisor → specialist → tool → Bedrock path and back, then drills into specific
use-case flows.

---

## 1. Component Overview (who talks to whom)

```mermaid
flowchart LR
    U([User / Browser]) -->|HTTPS| CF[CloudFront<br/>d2ci0urb01znvf]
    CF -->|static SPA| S3[(S3 SPA bucket)]
    CF -->|/api/*| ALB[ALB dev-alb]
    ALB --> FG[ECS Fargate<br/>backend :8000<br/>2 tasks]

    FG -->|authN| COG[Cognito<br/>dev-msp-assistant-users]
    FG -->|persist request| DDB[(DynamoDB<br/>chat-requests)]
    FG -->|EFS mount| EFS[(EFS shared state)]
    FG -->|HTTP invoke| SUP[AgentCore Runtime<br/>SUPERVISOR]

    SUP -->|A2A InvokeAgentRuntime| SPEC{{Specialist Agents<br/>security · cost · cloudwatch<br/>jira · knowledge · investigator · advisor}}
    SUP -->|InvokeModel| BR[Amazon Bedrock]
    SPEC -->|InvokeModel| BR
    SPEC -->|MCP over Gateway| GW[AgentCore Gateway<br/>AWS_IAM]
    SPEC -->|MCP + Cognito JWT| MCP[[MCP Tool Runtimes<br/>aws_api · aws_knowledge · cloudwatch]]

    GW --> TJ[Jira API]
    GW --> TAWS[AWS Control APIs]
    GW --> TCW[CloudWatch]

    SUP -->|events| MEM[(AgentCore Memory<br/>per-agent, STM)]
    SPEC -->|events| MEM
    SPEC -->|creds| ID[AgentCore Identity<br/>Token Vault]
    ID --> SM[(Secrets Manager)]

    SUP -.traces.-> OBS[CloudWatch Logs<br/>X-Ray / App Signals]
    SPEC -.traces.-> OBS
```

---

## 2. Full End-to-End Sequence (happy path)

This is the canonical flow for a single user question that requires one specialist.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant CF as CloudFront
    participant ALB as ALB (dev-alb)
    participant BE as Fargate Backend
    participant COG as Cognito
    participant DDB as DynamoDB
    participant SUP as Supervisor Runtime
    participant MEM as AgentCore Memory
    participant BR as Bedrock (LLM)
    participant SP as Specialist (A2A)
    participant GW as Gateway / MCP Tools
    participant EXT as External (AWS/Jira/CW)

    User->>CF: HTTPS request (chat message + JWT)
    CF->>ALB: forward /api/*
    ALB->>BE: route to backend :8000
    BE->>COG: validate user JWT
    COG-->>BE: token valid (claims)
    BE->>DDB: put chat request (request_id)
    BE->>SUP: InvokeAgentRuntime (HTTP) {prompt, session_id}

    SUP->>MEM: list recent events (short-term context)
    MEM-->>SUP: recent turns
    SUP->>BR: InvokeModel (route decision + reasoning)
    BR-->>SUP: "route to <specialist>"

    SUP->>SP: A2A InvokeAgentRuntime {prompt}
    SP->>MEM: list recent events (own memory)
    SP->>BR: InvokeModel (plan tool calls)
    BR-->>SP: tool call plan
    SP->>GW: MCP tool invoke (AWS_IAM / Cognito JWT)
    GW->>EXT: call downstream (read AWS / Jira / CW)
    EXT-->>GW: data
    GW-->>SP: tool result
    SP->>BR: InvokeModel (compose answer from tool data)
    BR-->>SP: specialist answer
    SP->>MEM: create event (turn record)
    SP-->>SUP: {response}

    SUP->>BR: InvokeModel (synthesize final answer)
    BR-->>SUP: final answer
    SUP->>MEM: create event (turn record)
    SUP-->>BE: {response}
    BE->>DDB: update request (status=complete)
    BE-->>ALB: HTTP 200 (answer)
    ALB-->>CF: response
    CF-->>User: rendered answer

    Note over SUP,SP: All hops emit logs to CloudWatch<br/>and spans to X-Ray / Application Signals
```

---

## 3. Supervisor Routing Logic (LangGraph)

How the supervisor decides which specialist(s) to call. Mirrors
`agents/supervisor/graph.py`.

```mermaid
flowchart TD
    A[Receive prompt] --> B[Load short-term memory]
    B --> C[LLM: analyze intent]
    C --> D{Which domain?}
    D -->|security| S1[route_to_specialist security]
    D -->|cost| S2[route_to_specialist cost]
    D -->|ops/metrics| S3[route_to_specialist cloudwatch]
    D -->|ticketing| S4[route_to_specialist jira]
    D -->|docs/KB| S5[route_to_specialist knowledge]
    D -->|incident/RCA| S6[route_to_specialist investigator]
    D -->|advice| S7[route_to_specialist advisor]
    D -->|multi-domain| M[Call several in order]

    S1 --> R[Collect specialist responses]
    S2 --> R
    S3 --> R
    S4 --> R
    S5 --> R
    S6 --> R
    S7 --> R
    M --> R
    R --> E{Enough to answer?}
    E -->|no| C
    E -->|yes| F[LLM: synthesize final answer]
    F --> G[Return response + write memory]
```

---

## 4. Specialist Agent Internal Loop (ReAct + MCP tools)

Every A2A specialist follows the same LangGraph ReAct loop
(`libs/common/graph.py` → `create_react_agent`).

```mermaid
flowchart TD
    A[Receive delegated request] --> B[Load memory context]
    B --> C[LLM reasons: need a tool?]
    C -->|yes| D[Select MCP tool + args]
    D --> E[Invoke via Gateway / MCP runtime]
    E --> F[Fetch creds from Token Vault if needed]
    F --> G[Downstream call: AWS / Jira / CloudWatch]
    G --> H[Return tool result to LLM]
    H --> C
    C -->|no more tools| I[LLM composes final answer]
    I --> J[Write turn to memory]
    J --> K[Return response to Supervisor]
```

---

## 5. Authentication & Authorization Flow

How identity flows across the layers (what is verified where).

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant SPA as SPA (Web Client)
    participant COG as Cognito
    participant BE as Backend
    participant SUP as Supervisor
    participant MCP as MCP Runtime
    participant VAULT as Token Vault

    User->>SPA: login
    SPA->>COG: auth (UserPoolWebClient)
    COG-->>SPA: user JWT (id/access token)
    SPA->>BE: API call + user JWT
    BE->>COG: verify JWT
    BE->>SUP: invoke (SigV4 / IAM identity)
    Note over SUP: Supervisor role holds<br/>InvokeA2ASpecialists (runtime/*)
    SUP->>MCP: MCP call
    Note over MCP: CUSTOM_JWT authorizer<br/>(M2M client, scope mcp-server/invoke)
    MCP->>VAULT: GetResourceApiKey / GetResourceOauth2Token
    VAULT-->>MCP: downstream credential (Jira, etc.)
```

---

## 6. Memory Write/Read Path (current: short-term only)

Reflects the deployed reality — per-agent memories are **STM only**
(`strategies: []`). Long-term (semantic/summary/episodic) is not yet wired to the
live runtimes.

```mermaid
flowchart LR
    subgraph Runtime
      A[Agent turn] -->|create_event| STM[(Short-Term Memory<br/>raw events, 30d)]
      A -->|list_events| STM
    end
    STM -. no strategies attached .-> LTM[(Long-Term Memory<br/>NOT CONFIGURED)]
    LTM -. would enable .-> SEM[Semantic facts]
    LTM -. would enable .-> SUM[Session summaries]
    LTM -. would enable .-> EPI[Episodic + reflection]

    style LTM stroke-dasharray: 5 5,stroke:#c0392b
    style SEM stroke-dasharray: 5 5
    style SUM stroke-dasharray: 5 5
    style EPI stroke-dasharray: 5 5
```

---

## 7. Error / Fallback Handling

```mermaid
flowchart TD
    A[Specialist tool call] --> B{Tool succeeded?}
    B -->|yes| C[Use result]
    B -->|timeout / error| D[LLM notes failure]
    D --> E{Retry viable?}
    E -->|yes, transient| F[Retry once]
    F --> B
    E -->|no| G[Return partial answer<br/>+ explain limitation]
    C --> H[Compose answer]
    G --> H
    H --> I[Supervisor synthesizes<br/>flags any gaps to user]
```

---

## 8. Notes on Fidelity

- Steps confirmed from control-plane discovery: runtime protocols (HTTP/A2A/MCP),
  supervisor `InvokeA2ASpecialists` IAM, Cognito JWT authorizer on MCP runtimes,
  gateway targets, per-agent STM memories, Bedrock model access, CloudWatch/X-Ray.
- Steps marked as backend behavior (DynamoDB write, Cognito verify, EFS use) are
  inferred from the resources + IAM and should be validated against the backend
  container code and the CDK stack.
- Exact per-agent Bedrock model IDs live in the deployment code, not the control
  plane; the diagrams show the generic `InvokeModel` interaction.
```
