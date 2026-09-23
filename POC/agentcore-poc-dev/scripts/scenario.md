# E‑Commerce Checkout RCA Scenario — Multi‑Signal, Multi‑Service

> **Intermittent checkout failures in a multi‑region e‑commerce platform.** Customers see checkout spin for 10–20s and occasionally fail. Only **~2.8%** of checkouts are affected. The system *looks* like it has a slow external payment provider — but the real root cause is **an infrastructure node‑image change that pinned a NIC RX‑queue interrupt to the wrong NUMA node**, stalling IPv6 DNS lookups deep in the payment path.
>
> This scenario is built to test whether an RCA engine does **real multi‑signal causal reasoning** (traces + metrics + logs, correlated by shared dimensions and time) rather than just picking the highest anomaly score. It deliberately plants **false leads**.

**Platform:** OpenObserve Enterprise · **org** `default` · **cluster** `prod-use1` · **region** `Region-B` (the affected region)

---

## 1. The story in one paragraph

Checkout success rate drops from **99.97% → 97.2%**, isolated to `region=Region-B`, `payment_method=CARD`, `device_type=MOBILE`. Checkout p99 latency spikes to **~18s** — but only for `checkout_version=v4.18.7`, `currency=INR`, `cart_items > 12`. Traces show the slow span is **payment‑service → external payment‑provider (~17s)** — *but other apps calling the same provider are fine*, so the provider is a **false lead**. Drilling down: 4 payment pods (all on **node_pool NP‑17**) show connection‑pool exhaustion; DNS **AAAA (IPv6)** lookups on NP‑17 take **3.2s** (A‑records fine); kernel telemetry shows **RX‑queue‑7 latency of 2.8s**; and an infra change rolled **node image `2026.06.18`** onto NP‑17 that set **IRQ affinity RX‑7 → CPU48 (NUMA node 1)** while the NIC queue memory lives on **NUMA node 0** — a cross‑NUMA stall. A two‑week‑old **payment‑risk feature** (`CARD + INR + cart>12`) issues 6–12 DNS lookups per request, which is why *only that dimension* is affected.

---

## 2. Topology & the causal chain

```
Users → CDN/WAF → Global LB → API Gateway
                                   │
                                   ▼
                            checkout-service ──► pricing / inventory / promotion / order
                                   │
                                   ▼
                            payment-service ──► token-service, fraud-service
                                   │
                                   ▼
                        external payment-provider (payments.provider.com)   ← looks slow (FALSE LEAD)

Underneath (the real chain, bottom-up):
 node-image 2026.06.18 (NP-17)  →  IRQ affinity RX-7 → CPU48 (NUMA1), queue mem NUMA0 (cross-NUMA)
   →  RX-queue-7 latency 2.8s  →  slow UDP recv  →  AAAA (IPv6) DNS latency 3.2s
   →  payment HTTP connection-pool exhaustion + retries  →  payment tail latency ~17s
   →  checkout tail latency ~18s  →  checkout SLO breach (99.97% → 97.2%)
```

**Root cause:** a node‑image deployment introduced an incorrect **IRQ‑affinity / cross‑NUMA NIC‑queue** configuration. A high‑cardinality request pattern (`CARD+INR+cart>12`) amplified DNS traffic enough to expose it.
**Resolution:** roll back the NP‑17 node image (2026.06.18 → 2026.05.30) and fix IRQ affinity so the RX queue's interrupt runs on the same NUMA node as its memory.

---

## 3. Signals involved

Everything correlates on shared dimensions — primarily **`cluster` + `region`**, then **`node_pool` / `pod` / `nic_queue`** as the drill‑down narrows to the failing hardware.

### 3.1 Traces — stream `ecom_traces`

A dedicated trace stream (not the default). One distributed trace per checkout, spanning **9 services**.

**Service call graph (client → server):**

```
checkout-service (SERVER "POST /checkout")
 ├─► pricing-service    (GET /price)      ~20ms
 ├─► inventory-service  (GET /stock)      ~35ms
 ├─► promotion-service  (GET /promo)      ~15ms
 ├─► order-service      (POST /order)     ~40ms
 └─► payment-service    (POST /pay)       normal ~70ms | SLOW ~17.8s
       ├─► token-service   (token lookup) ~30ms
       ├─► fraud-service   (fraud check)  ~45ms
       └─► payment-provider (HTTP POST payments.provider.com)  normal ~60ms | SLOW ~17s
```

**Span structure & key attributes:**

| Span (service · name · kind) | Key span attributes | Normal | Slow (affected combo) |
|---|---|---|---|
| `checkout-service` · `POST /checkout` · SERVER | `region`, `cluster`, `payment_method`, `currency`, `cart_items`, `checkout_version`, `http.route` | 200 ms | **18,000 ms** |
| `checkout-service` · `payment call` · CLIENT | `peer.service=payment-service` | — | drives the payment edge |
| `payment-service` · `POST /pay` · SERVER | `pod`, `node_pool`, `availability_zone`, `version`, `peer.service` | 70 ms | **17,800 ms** |
| `payment-service` · `HTTP POST payments.provider.com` · CLIENT | `peer.service=payment-provider`, `net.peer.name`, `dns.query_type=AAAA`, `dns.server` | 60 ms | **17,000 ms** |
| `token-service`, `fraud-service` · SERVER | `peer.service` | 30 / 45 ms | normal (rules them out) |

Resource attributes on every span: `service.name`, `service_host_name`, `cluster`, `region`.
The **client→server span pairs** (CLIENT `peer.service` → child SERVER) are what build the service‑dependency graph: `checkout-service → payment-service → payment-provider`.

### 3.2 Metrics (each metric name = its own stream)

Grouped by the layer they belong to. **Role** = `SYMPTOM` (what's reported) · `EVIDENCE` (proves the chain) · `DECOY` (looks guilty / normal, must be ruled out).

**Level 1 — Business SLO**

| Metric stream | Dimensions | Normal → Anomaly | Role |
|---|---|---|---|
| `checkout_success_rate` | `region, country, tenant_id, customer_tier, payment_method, device_type, application_version, cluster` | 99.97% → **97.2%** (Region‑B / CARD / MOBILE) | **SYMPTOM** |

**Level 2 — Checkout service latency & infra**

| Metric stream | Dimensions | Normal → Anomaly | Role |
|---|---|---|---|
| `checkout_latency_p99_ms` | `region, checkout_version, payment_method, currency, cart_items, cluster` | 240 → **18,000 ms** (Region‑B / INR / cart>12) | **SYMPTOM** |
| `checkout_latency_p95_ms` | same | 900 → ~1,200 ms | EVIDENCE |
| `checkout_latency_p50_ms` | same | ~180 ms (flat) | EVIDENCE |
| `checkout_cpu_percent` | `region, service, cluster` | ~42% (flat) | **DECOY** (not compute‑bound) |
| `checkout_mem_percent` | same | ~58% (flat) | **DECOY** |
| `checkout_gc_pause_ms` | same | ~8 ms (flat) | **DECOY** |
| `checkout_request_rate_rps` | same | ~12,000 (flat) | **DECOY** (traffic normal) |

**Level 4 — Payment pod / connection pool**

| Metric stream | Dimensions | Normal → Anomaly | Role |
|---|---|---|---|
| `payment_connection_acquire_ms` | `pod, node, availability_zone, region, version, node_pool, node_image_version, cluster` | 25 → **4,321 ms** (4 pods on NP‑17) | **EVIDENCE** |
| `payment_pool_exhausted_count` | same | 0 → **7** | EVIDENCE |
| `payment_provider_latency_ms` | `pod, provider, region, cluster` | 70 → **17,000 ms** | **DECOY** (only *this* app affected → not the provider) |

**Level 6 — DNS**

| Metric stream | Dimensions | Normal → Anomaly | Role |
|---|---|---|---|
| `dns_query_latency_p99_ms` | `node_pool, dns_server, query_type, response_code, region, cluster` | A: 12 ms · **AAAA on NP‑17: 3,200 ms** | **EVIDENCE** (only IPv6 slow) |
| `dns_query_rate` | same | 1,200 → **8,200** (AAAA on NP‑17) | EVIDENCE (risk‑feature amplification) |

**Level 7–9 — Network, kernel/eBPF, IRQ/NUMA**

| Metric stream | Dimensions | Normal → Anomaly | Role |
|---|---|---|---|
| `node_nic_mtu` | `node_pool, nic, cluster` | 1,500 healthy · **9,000 on NP‑17** | **DECOY** (MTU mismatch, but DNS packets are small) |
| `net_tcp_rtt_ms` | `node_pool, cluster` | ~0.8 ms (flat) | **DECOY** |
| `net_udp_packet_loss_pct` | same | ~0.01% (flat) | **DECOY** |
| `net_bandwidth_mbps` | same | ~240 (flat) | **DECOY** |
| `kernel_rx_queue_latency_ms` | `node_pool, nic_queue, numa_node, node, cluster` | ~0 · **RX‑7 = 2,800 ms** | **EVIDENCE** |
| `kernel_udp_recvmsg_latency_ms` | `node_pool, nic_queue, numa_node, cpu, cluster` | ~0 → **2,750 ms** | EVIDENCE |
| `irq_affinity_numa_mismatch` | `node_pool, nic_queue, irq_cpu, irq_numa, queue_mem_numa, node_image_version, cluster` | 0 → **1** (RX‑7 IRQ=CPU48/NUMA1, mem=NUMA0) | **ROOT‑CAUSE ANCHOR** |
| `softirq_cpu_usage_percent` | `node_pool, cpu, numa_node, cluster` | 12% → **88%** (CPU48) | EVIDENCE |

### 3.3 Logs (stream · logger · message)

| Log stream | Logger / level | Representative message | Role |
|---|---|---|---|
| `payment_service_logs` | `payment.client` WARN | `Payment provider request timeout` | SYMPTOM (misleading → looks like provider) |
| | `payment.retry` ERROR | `Retry attempt 2/3` | EVIDENCE (retry storm) |
| | `http.connection` WARN | `Connection acquisition took 4321ms` | EVIDENCE (pool exhaustion) |
| | `dns.resolver` WARN *(rare, ~1/50k)* | `DNS resolution exceeded expected latency hostname=payments.provider.com query=AAAA latency=3100ms` | **KEY LEAD** (the smoking gun) |
| `checkout_service_logs` | `checkout.orchestrator` WARN | `Downstream payment call slow (…ms) region=Region-B currency=INR cart_items=…` | EVIDENCE (dimension isolation) |
| `kernel_logs` | `kernel.net` WARN | `RX queue 7 processing latency high (2800ms) cpu=48 numa=1 (queue memory numa=0 cross-NUMA)` | **EVIDENCE** (the cross‑NUMA proof) |
| `infra_change_logs` | `infra.automation` INFO | `Node pool NP-17 rolled to node image 2026.06.18 (IRQ balancing configuration applied)` | **ROOT‑CAUSE CHANGE EVENT** |
| | `infra.automation` WARN | `IRQ affinity set: RX-7 -> CPU48 (NUMA node 1); NIC queue memory on NUMA node 0` | ROOT‑CAUSE CHANGE EVENT |
| | `deploy.app` INFO *(~14 days prior)* | `Deployed payment-risk feature: extra risk check for CARD+INR+cart_items>12 (adds DNS lookups)` | AMPLIFIER (why only this dimension) |

---

## 4. The false leads (deliberately planted)

A naïve "highest anomaly" approach gets these wrong — a good RCA must reason past them:

1. **External payment provider looks slow (17s)** — but `payment_provider_latency_ms` is only high for *this* app's affected pods; other consumers are fine → **not the provider**.
2. **MTU mismatch (9000 vs 1500 on NP‑17)** — real config difference, but DNS packets are small → doesn't explain it.
3. **"High CPU"/normal infra** — `checkout_cpu/mem/gc/request_rate` are all normal → not compute, memory, GC, or traffic.
4. **"Payment timeout" logs** — point at the provider, not the local DNS/NUMA stall.

---

## 5. Root cause & resolution

- **Root cause:** node‑image `2026.06.18` on **node_pool NP‑17** applied an **incorrect IRQ‑affinity** config — RX‑queue‑7's interrupt pinned to **CPU48 (NUMA node 1)** while the NIC queue memory sits on **NUMA node 0**. Cross‑NUMA memory access delayed RX processing → slow UDP/DNS **AAAA** responses → payment connection‑pool exhaustion + retries → payment & checkout tail latency → SLO breach.
- **Amplifier:** the `CARD + INR + cart>12` payment‑risk feature issues 6–12 DNS lookups per request (vs 1 normally), so only that dimension generated enough AAAA traffic to expose the RX‑queue stall.
- **Blast radius:** the 4 pods (`payment-pod-118/124/131/144`) that the scheduler placed on NP‑17 nodes built from the bad image.
- **Fix:** roll NP‑17 back to node image `2026.05.30`; correct IRQ affinity (same‑NUMA CPU for the RX queue).

---

## 6. Reproduce it in PostgreSQL — `dump_scenario_postgres.sh`

To mimic this scenario in a **PostgreSQL** environment (e.g. a new customer running their own store), the repo ships `dump_scenario_postgres.sh`. It generates the full data set (every trace, metric, and log above) and loads it into Postgres, **tagged per tenant**. Pass multiple tenants and the *same* data is inserted for each.

**Requirements:** `python3` (standard library only) and `psql` on `PATH` — nothing else. The script checks for both on startup and, if either is missing, prints the exact install command for your OS (apt / dnf-yum / brew) and how to add it to `PATH` before exiting.

### 7.1 Table schemas it creates

Three tables (created `IF NOT EXISTS`, in your `--schema`, default `public`):

```sql
CREATE TABLE <schema>.otel_metrics (
  tenant_id   text NOT NULL,
  ts          timestamptz NOT NULL,
  metric_name text NOT NULL,        -- e.g. checkout_success_rate, dns_query_latency_p99_ms
  value       double precision,
  labels      jsonb                 -- dimensions: region, cluster, node_pool, pod, query_type, ...
);
CREATE INDEX otel_metrics_tenant_metric_ts ON <schema>.otel_metrics (tenant_id, metric_name, ts);

CREATE TABLE <schema>.otel_logs (
  tenant_id   text NOT NULL,
  ts          timestamptz NOT NULL,
  stream      text NOT NULL,        -- payment_service_logs, checkout_service_logs, kernel_logs, infra_change_logs
  level       text,                 -- WARN / ERROR / INFO
  logger      text,                 -- payment.client, dns.resolver, kernel.net, infra.automation, ...
  message     text,
  attributes  jsonb
);
CREATE INDEX otel_logs_tenant_stream_ts ON <schema>.otel_logs (tenant_id, stream, ts);

CREATE TABLE <schema>.otel_spans (
  tenant_id      text NOT NULL,
  trace_id       text NOT NULL,
  span_id        text NOT NULL,
  parent_span_id text,              -- NULL on the root (checkout) span
  service_name   text,              -- checkout-service, payment-service, payment-provider, ...
  span_name      text,              -- POST /checkout, POST /pay, HTTP POST payments.provider.com, ...
  span_kind      text,              -- SERVER / CLIENT
  start_time     timestamptz,
  end_time       timestamptz,
  duration_ms    double precision,
  attributes     jsonb              -- peer.service, dns.query_type, dns.server, node_pool, pod, ...
);
CREATE INDEX otel_spans_tenant_trace  ON <schema>.otel_spans (tenant_id, trace_id);
CREATE INDEX otel_spans_tenant_svc_ts ON <schema>.otel_spans (tenant_id, service_name, start_time);
```

**Rows per tenant** (default 60-min window): ~**12,120** metric rows · ~**286** log rows · ~**840** spans.

### 7.2 How to run

```bash
# single tenant (prompts for the password)
./dump_scenario_postgres.sh --host db.internal --port 5432 --db observability \
    --user rca --tenants "acme"

# multiple tenants — same data inserted for each — custom schema, idempotent re-run
PGPASSWORD='secret' ./dump_scenario_postgres.sh \
    --host 10.0.0.5 --port 5432 --db obs --user rca \
    --schema rca_demo --tenants "acme,globex,initech" --truncate
```

| Flag | Meaning | Default |
|---|---|---|
| `--host` / `--port` / `--db` / `--user` / `--password` | Postgres connection (or use standard `PG*` env vars) | localhost / 5432 / postgres / postgres |
| `--tenants` | **Required.** Comma-separated tenant IDs; the same data is inserted for each | — |
| `--schema` | Target schema | `public` |
| `--window-mins` | Length of the data time-window in minutes | 60 |
| `--truncate` | Delete this tenant's existing rows in the 3 tables first (idempotent re-runs) | off |

The script generates the SQL, loads it in a single transaction via `psql`, and prints per-tenant row counts at the end.

**Notes**
- Timestamps are **relative to run time**, so the data always looks recent.
- **Multi-tenant:** every tenant gets an identical copy of the data; only `tenant_id` differs.
- The scenario's internal business dimension is stored in `labels` as `account_id` (to avoid clashing with the `tenant_id` partition column).

### 7.3 Verify the RCA chain in SQL

```sql
SET search_path TO public;      -- or your --schema, e.g. rca_demo
\set t 'acme'                   -- the tenant to inspect

-- 1) SLO drop is isolated to Region-B / CARD / MOBILE
SELECT labels->>'region' AS region, labels->>'payment_method' AS pm,
       labels->>'device_type' AS dev, round(avg(value)::numeric,2) AS success_pct
FROM otel_metrics WHERE tenant_id = :'t' AND metric_name = 'checkout_success_rate'
GROUP BY 1,2,3 ORDER BY success_pct LIMIT 5;

-- 2) Only IPv6 (AAAA) DNS is slow, and only on NP-17
SELECT labels->>'node_pool' AS node_pool, labels->>'query_type' AS qtype,
       round(max(value)::numeric,0) AS p99_ms
FROM otel_metrics WHERE tenant_id = :'t' AND metric_name = 'dns_query_latency_p99_ms'
GROUP BY 1,2 ORDER BY p99_ms DESC LIMIT 4;

-- 3) The cross-NUMA RX queue latency + the IRQ-mismatch flag
SELECT metric_name, labels->>'nic_queue' AS queue, round(max(value)::numeric,0) AS v
FROM otel_metrics WHERE tenant_id = :'t'
  AND metric_name IN ('kernel_rx_queue_latency_ms','irq_affinity_numa_mismatch')
GROUP BY 1,2 ORDER BY v DESC LIMIT 5;

-- 4) The root-cause change event
SELECT ts, message FROM otel_logs
WHERE tenant_id = :'t' AND stream = 'infra_change_logs' ORDER BY ts;

-- 5) The slow trace chain (payment-provider ~17s is the deepest slow span)
SELECT service_name, span_name, span_kind, round(max(duration_ms)::numeric,0) AS ms
FROM otel_spans WHERE tenant_id = :'t'
GROUP BY 1,2,3 ORDER BY ms DESC LIMIT 8;
```
