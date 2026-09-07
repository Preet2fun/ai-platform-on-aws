# AI-PLATFORM — AgentCore Architecture & Best-Practice Reference

An **independent, standalone reference** for designing agentic AI on **Amazon Bedrock
AgentCore**. It captures architecture, design principles, and best practices — built from
research (AWS blogs, webinars, workshops, production examples) and industry standards.

## What this is (and isn't)

- ✅ A **use-case-agnostic** standard for AgentCore architecture components.
- ✅ Organized by **AgentCore component**, each evaluated through the **6 AWS
  Well-Architected pillars**.
- ✅ Built **component by component** from research, with **sources cited**.
- ❌ **Not** dependent on, and contains **no references to**, the `POC/` or `PRODUCTION/`
  folders.
- ❌ **Not** tied to any specific use case. Generic, neutral examples only.

> This folder is the **standard**. `POC/` is where ad-hoc learning happens and is
> gap-analyzed *against* this standard. `PRODUCTION/` is where real use cases are built
> *using* this standard. Neither couples back into this folder.

## Structure

```
AI-PLATFORM/
├── README.md                  # this file
├── well-architected/          # the 6-pillar lens applied to agentic AI on AgentCore
├── principles/                # component-agnostic design principles
├── reference-architecture/    # the generic target architecture (component composition)
├── standards/                 # conventions: naming, tagging, IaC, versioning
├── _component-template/        # the template every component folder follows
└── <component>/               # one folder per AgentCore component (see below)
    ├── README.md              # component described once, then the 6-pillar analysis
    ├── examples/              # generic, neutral examples
    └── reference/             # source/background material
```

### Components (built step by step)

| Component | Purpose | Status |
|---|---|---|
| **guardrails** | Policy Engine + guardrails: control input, authz, tools, output, bypass | ✅ authored |
| **memory** | Short-term + long-term strategies (semantic, summarization, preference, episodic) | ✅ authored |
| **runtime** | Hosting and scaling agents; protocols; lifecycle | ☐ planned |
| **gateway** | Turning APIs/tools into MCP tools; targets; auth | ☐ planned |
| **identity** | Inbound auth + outbound credentials (token vault) | ☐ planned |
| **observability** | Tracing, metrics, logging for agents | ☐ planned |
| **evaluations** | Automated agent quality assessment | ☐ planned |

## How every component is documented

Each component folder describes the component **once**, then analyzes it through the six
pillars: **Security · Reliability · Operational Excellence · Performance Efficiency · Cost
Optimization · Sustainability**. See `_component-template/` for the exact shape.

## Rules for this folder
1. Component × 6-pillar structure.
2. Use-case-agnostic; neutral examples only (no specific business/domain framing).
3. No references to `POC/` or `PRODUCTION/`.
4. Cite sources (AWS docs, blogs, workshops) inline.
5. Verify facts against current AWS documentation before writing.

## Sources
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
