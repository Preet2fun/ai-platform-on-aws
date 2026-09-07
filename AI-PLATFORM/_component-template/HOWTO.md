# How to add a new component

1. Copy `_component-template/` to `<component>/` (e.g. `runtime/`, `gateway/`, `identity/`,
   `observability/`, `evaluations/`).
2. Fill `README.md`:
   - Describe the component **once** (overview + verified mechanics with source links).
   - Then the **6-pillar analysis** (Security, Reliability, Operational Excellence,
     Performance Efficiency, Cost Optimization, Sustainability), applying the definitions
     in `../well-architected/`.
   - Add a design checklist and a Sources section.
3. Add `examples/` — generic, neutral examples only (no use-case or account specifics).
4. Add `reference/` — source/background material.
5. Update the component table in `../README.md` (mark status).
6. Verify every fact against current AWS documentation (use the AgentCore docs tools).

## Rules (enforced by steering)
- Component × 6-pillar structure.
- Use-case-agnostic; neutral examples (no SRE/RCA/SOC or any domain framing unless the
  user explicitly asks for an example).
- No references to `POC/` or `PRODUCTION/`.
- Cite sources inline; rephrase source content for compliance (no long verbatim quotes).
