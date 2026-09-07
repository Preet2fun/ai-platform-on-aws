# Sources — Memory Component

The memory guidance in this folder is grounded in the following AWS sources. Content was
rephrased for compliance; verify facts against current AWS documentation before building.

## Primary sources

**[1] Amazon Bedrock AgentCore Memory: Building context-aware agents**
https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/
- The memory problem (context window, state, recall, persistence-without-intelligence).
- Five design principles: abstracted storage, security (encryption at rest/in transit),
  continuity, data organization/access control, scalability/performance.
- Core components: memory resource (`eventExpiryDuration` up to 365 days, AWS-managed or
  customer-managed KMS), short-term memory (immutable events by `actorId`+`sessionId`;
  Conversational vs blob; only Conversational feeds LTM), long-term memory (async),
  namespaces, memory strategies.
- Built-in strategies: Semantic, Summary, User Preference (all ignore PII by default).
- Advanced features: branching (`rootEventId`), checkpointing (blob, excluded from LTM).
- Best practices: structured architecture, strategy selection, retrieve→reason→store,
  security/privacy (IAM least-privilege, CMK, guardrails vs injection/poisoning),
  observability.

**[2] Building smarter AI agents: AgentCore long-term memory deep dive**
https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/
- Extraction (async, LLM-driven, keeps meaningful vs routine).
- Consolidation: ADD / UPDATE / NO-OP; recency wins; outdated marked INVALID (audit
  trail); handles out-of-order events and failures (backoff; add-on-failure to avoid loss).
- Customization: built-in-with-overrides (custom prompt + model), self-managed + Batch APIs.
- Benchmarks (LoCoMo, LongMemEval, PrefEval, PolyBench-QA): ~89–95% compression rates.
- Performance: extraction/consolidation ~20–40s; retrieval ~200ms; parallel strategies.

**[3] Build agents to learn from experiences using AgentCore episodic memory**
https://aws.amazon.com/blogs/machine-learning/build-agents-to-learn-from-experiences-using-amazon-bedrock-agentcore-episodic-memory/
- Episodic pipeline: turn extraction → episode extraction → cross-episode reflection.
- Turn fields (situation, intent, action, thought, assessment, goal assessment); episode
  fields (situation, intent, success eval, justification, insights); reflection (use case,
  hints, confidence 0.1–1.0).
- Custom overrides (prompts, model), namespaces (reflection namespace is a sub-path of the
  episode namespace).
- Episodic completes the framework alongside summarization, semantic, and preference.

## Supporting
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [Amazon Bedrock AgentCore Memory Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
