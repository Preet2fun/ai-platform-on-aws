#!/usr/bin/env bash
#
# dump_scenario_postgres.sh
# ---------------------------------------------------------------------------
# Generates the "E-commerce checkout / cross-NUMA IRQ" RCA scenario data
# (traces + metrics + logs, exactly as described in scenario.md) and loads it
# into PostgreSQL, tagged by tenant_id.
#
# Multi-tenant: pass one or more tenant IDs via --tenants. The SAME scenario
# data set is inserted for every tenant (so a new customer can mimic the RCA
# scenario per-tenant in their own Postgres-backed environment).
#
# Tables created (schema-qualified, IF NOT EXISTS):
#   <schema>.otel_metrics(tenant_id, ts, metric_name, value, labels jsonb)
#   <schema>.otel_logs   (tenant_id, ts, stream, level, logger, message, attributes jsonb)
#   <schema>.otel_spans  (tenant_id, trace_id, span_id, parent_span_id,
#                         service_name, span_name, span_kind,
#                         start_time, end_time, duration_ms, attributes jsonb)
#
# Requirements: python3 (stdlib only) and psql on PATH.
# ---------------------------------------------------------------------------
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  dump_scenario_postgres.sh --tenants "t1,t2,..." [connection options] [data options]

PostgreSQL connection (fall back to standard PG* env vars if omitted):
  --host HOST         Postgres host           (default: $PGHOST or localhost)
  --port PORT         Postgres port           (default: $PGPORT or 5432)
  --db   DBNAME       Database name           (default: $PGDATABASE or postgres)
  --user USER         Username                (default: $PGUSER or postgres)
  --password PASS     Password (or set $PGPASSWORD; prompted if omitted)

Data options:
  --tenants LIST      REQUIRED. Comma-separated tenant IDs. The same scenario
                      data is inserted for EACH tenant, e.g. "acme,globex,initech".
  --schema NAME       Target schema           (default: public)
  --window-mins N     Data time-window length in minutes (default: 60)
  --truncate          Delete this tenant's existing rows in the 3 tables before
                      inserting (makes re-runs idempotent per tenant).
  -h, --help          Show this help.

Examples:
  # single tenant
  ./dump_scenario_postgres.sh --host db.internal --db observability \
      --user rca --password 'secret' --tenants "acme"

  # multiple tenants, idempotent, custom schema
  PGPASSWORD='secret' ./dump_scenario_postgres.sh --host 10.0.0.5 --db obs \
      --user rca --schema rca_demo --tenants "acme,globex,initech" --truncate

Note: passing --password on the CLI is visible in the process list; prefer the
PGPASSWORD env var or the interactive prompt for real credentials.
USAGE
}

# --- dependency checks with install / PATH guidance ---
detect_pkg_mgr() {
  if [[ "$(uname -s)" == "Darwin" ]]; then echo "brew"; return; fi
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case " ${ID:-} ${ID_LIKE:-} " in
      *debian*|*ubuntu*)                                   echo "apt"; return;;
      *rhel*|*fedora*|*centos*|*rocky*|*almalinux*|*amzn*) echo "dnf"; return;;
    esac
  fi
  echo "unknown"
}

require_cmd() {
  local cmd="$1" pretty="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "   [ok] ${pretty}: $(command -v "$cmd")"
    return 0
  fi
  local pm; pm="$(detect_pkg_mgr)"
  {
    echo ""
    echo "ERROR: '${cmd}' (${pretty}) is required but was NOT found on PATH."
    echo ""
    echo "  1) Install it:"
    case "${cmd}:${pm}" in
      python3:apt)  echo "       sudo apt-get update && sudo apt-get install -y python3";;
      python3:dnf)  echo "       sudo dnf install -y python3          # or: sudo yum install -y python3";;
      python3:brew) echo "       brew install python3";;
      python3:*)    echo "       install 'python3' with your OS package manager";;
      psql:apt)     echo "       sudo apt-get update && sudo apt-get install -y postgresql-client";;
      psql:dnf)     echo "       sudo dnf install -y postgresql       # client tools; or: sudo yum install -y postgresql";;
      psql:brew)    echo "       brew install libpq                   # (or: brew install postgresql)";;
      psql:*)       echo "       install the PostgreSQL client ('psql') with your OS package manager";;
    esac
    echo ""
    echo "  2) If it is already installed but not on PATH, add its bin dir to PATH and re-run, e.g.:"
    if [[ "$cmd" == "psql" ]]; then
      echo "       export PATH=\"/usr/lib/postgresql/16/bin:\$PATH\"     # Debian/Ubuntu (match your version)"
      echo "       export PATH=\"/usr/pgsql-16/bin:\$PATH\"              # RHEL/Rocky/Alma PGDG (match your version)"
      echo "       export PATH=\"\$(brew --prefix libpq)/bin:\$PATH\"    # macOS Homebrew"
    else
      echo "       export PATH=\"/usr/local/bin:\$PATH\"                 # wherever python3 was installed"
    fi
    echo "       # persist it by appending that 'export' line to ~/.bashrc (bash) or ~/.zshrc (zsh)"
    echo "       # then verify with:  command -v ${cmd}"
    echo ""
  } >&2
  exit 1
}

# --- defaults (honour standard PG* env vars) ---
HOST="${PGHOST:-localhost}"; PORT="${PGPORT:-5432}"; DB="${PGDATABASE:-postgres}"
USER="${PGUSER:-postgres}"; PASSWORD="${PGPASSWORD:-}"; SCHEMA="public"
TENANTS=""; WINDOW_MINS=60; TRUNCATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)        HOST="$2"; shift 2;;
    --port)        PORT="$2"; shift 2;;
    --db|--database) DB="$2"; shift 2;;
    --user)        USER="$2"; shift 2;;
    --password)    PASSWORD="$2"; shift 2;;
    --tenants)     TENANTS="$2"; shift 2;;
    --schema)      SCHEMA="$2"; shift 2;;
    --window-mins) WINDOW_MINS="$2"; shift 2;;
    --truncate)    TRUNCATE=1; shift;;
    -h|--help)     usage; exit 0;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 1;;
  esac
done

[[ -z "$TENANTS" ]] && { echo "ERROR: --tenants is required" >&2; usage; exit 1; }

echo ">> Checking prerequisites (python3, psql) ..."
require_cmd python3 "Python 3"
require_cmd psql    "PostgreSQL client (psql)"

if [[ -z "$PASSWORD" ]]; then
  read -rsp "PostgreSQL password for ${USER}@${HOST}:${PORT}/${DB}: " PASSWORD; echo
fi

SQL_FILE="$(mktemp -t ecom_rca_scenario.XXXXXX.sql)"
trap 'rm -f "$SQL_FILE"' EXIT

echo ">> Generating scenario SQL  (tenants: ${TENANTS} | window: ${WINDOW_MINS}m | schema: ${SCHEMA} | truncate: ${TRUNCATE})"
SCENARIO_TENANTS="$TENANTS" SCENARIO_SCHEMA="$SCHEMA" SCENARIO_WINDOW_MINS="$WINDOW_MINS" SCENARIO_TRUNCATE="$TRUNCATE" \
python3 - > "$SQL_FILE" <<'PYEOF'
import os, json, time, random

random.seed(1042)
SCHEMA = os.environ.get("SCENARIO_SCHEMA", "public")
TENANTS = [t.strip() for t in os.environ["SCENARIO_TENANTS"].split(",") if t.strip()]
WMIN   = int(os.environ.get("SCENARIO_WINDOW_MINS", "60"))
TRUNC  = os.environ.get("SCENARIO_TRUNCATE", "0") == "1"

NOW = int(time.time()); WIN = NOW - WMIN*60
IRQ = NOW - int(WMIN*60*35/60)   # infra change / IRQ-affinity onset
SYM = NOW - int(WMIN*60*33/60)   # customer-visible symptom onset
STEP = 60

# ---- shared identity (mirrors scenario.md) ----
CLUSTER="prod-use1"; BAD_REGION="Region-B"; REGIONS=["Region-A","Region-B","Region-C"]
BAD_AZ="B2"; BAD_NP="NP-17"; BAD_IMG="2026.06.18"; GOOD_IMG="2026.05.30"
BAD_PODS=["payment-pod-118","payment-pod-124","payment-pod-131","payment-pod-144"]
ALL_PODS=BAD_PODS+[f"payment-pod-{n}" for n in (101,107,112,119,127,133,140,151)]
BAD_DNS="10.20.4.53"; PAY_VER="v7.31"; CHK_VER="v4.18.7"

metrics=[]; logs=[]; spans=[]
def M(name,ts,val,lb): metrics.append((name,ts,float(val),lb))
def L(stream,ts,level,logger,msg,extra):
    a={"cluster":CLUSTER,"region":BAD_REGION}; a.update(extra); logs.append((stream,ts,level,logger,msg,a))
def hexid(n): return "".join(random.choice("0123456789abcdef") for _ in range(n))
def S(tid,sid,parent,service,name,kind,start_s,dur_ms,attr):
    a={"region":BAD_REGION,"cluster":CLUSTER}; a.update(attr)
    spans.append((tid,sid,parent,service,name,("SERVER" if kind==2 else "CLIENT"),
                  start_s, start_s+dur_ms/1000.0, dur_ms, a))

# ===================== METRICS =====================
# L1 - business SLO
countries=["US","IN","GB","DE","BR"]; tiers=["gold","silver","bronze"]
pms=["CARD","UPI","WALLET"]; devices=["MOBILE","DESKTOP"]; appvers=["v4.18.7","v4.18.6","v4.17.9"]
for ts in range(WIN,NOW,STEP):
    for region in REGIONS:
        for pm in pms:
            for dev in devices:
                if region==BAD_REGION and pm=="CARD" and dev=="MOBILE" and ts>=SYM:
                    base=97.2+random.uniform(-0.3,0.3)
                else:
                    base=99.97+random.uniform(-0.02,0.01)
                M("checkout_success_rate",ts,round(base,3),{"region":region,"country":random.choice(countries),
                    "account_id":f"acct-{random.randint(1,40)}","customer_tier":random.choice(tiers),
                    "payment_method":pm,"device_type":dev,"application_version":random.choice(appvers),"cluster":CLUSTER})
# L2 - checkout latency + normal infra (decoys)
currencies=["USD","INR","EUR","GBP"]; carts=["1-4","5-12","12+"]
for pname,normal,spike in [("checkout_latency_p50_ms",180,190),("checkout_latency_p95_ms",900,1200),("checkout_latency_p99_ms",240,18000)]:
    for ts in range(WIN,NOW,STEP):
        for region in REGIONS:
            for cur in currencies:
                for cart in carts:
                    hot=(region==BAD_REGION and cur=="INR" and cart=="12+" and ts>=SYM)
                    if hot and pname=="checkout_latency_p99_ms": val=spike*random.uniform(0.85,1.05)
                    elif not hot: val=normal*random.uniform(0.9,1.1)
                    else: val=normal*random.uniform(1.0,1.3)
                    M(pname,ts,round(val,1),{"region":region,"checkout_version":(CHK_VER if region==BAD_REGION else "v4.18.6"),
                        "payment_method":"CARD","currency":cur,"cart_items":cart,"cluster":CLUSTER})
for pname,b in [("checkout_cpu_percent",42),("checkout_mem_percent",58),("checkout_gc_pause_ms",8),("checkout_request_rate_rps",12000)]:
    for ts in range(WIN,NOW,STEP):
        M(pname,ts,round(b*random.uniform(0.92,1.08),2),{"region":BAD_REGION,"service":"checkout-service","cluster":CLUSTER})
# L4 - payment pod / pool + provider false-lead
for pname,normal,spike in [("payment_connection_acquire_ms",25,4321),("payment_pool_exhausted_count",0,7)]:
    for ts in range(WIN,NOW,STEP):
        for pod in ALL_PODS:
            bad=pod in BAD_PODS and ts>=SYM
            val=(spike*random.uniform(0.7,1.1)) if bad else (normal*random.uniform(0.8,1.2))
            M(pname,ts,round(val,1),{"pod":pod,"node":("node-np17-"+pod[-1] if pod in BAD_PODS else "node-np09-"+pod[-1]),
                "availability_zone":(BAD_AZ if pod in BAD_PODS else "A1"),"region":BAD_REGION,"version":PAY_VER,
                "node_pool":(BAD_NP if pod in BAD_PODS else "NP-09"),
                "node_image_version":(BAD_IMG if pod in BAD_PODS else GOOD_IMG),
                "service":"payment-service","cluster":CLUSTER})
for ts in range(WIN,NOW,STEP):
    for pod in ALL_PODS:
        bad=pod in BAD_PODS and ts>=SYM
        M("payment_provider_latency_ms",ts,round((17000*random.uniform(0.9,1.05)) if bad else 70*random.uniform(0.8,1.2),1),
            {"pod":pod,"provider":"payments.provider.com","region":BAD_REGION,"service":"payment-service","cluster":CLUSTER})
# L6 - DNS
for pname in ["dns_query_latency_p99_ms","dns_query_rate"]:
    for ts in range(WIN,NOW,STEP):
        for np_ in [BAD_NP,"NP-09","NP-05"]:
            for qt in ["A","AAAA"]:
                bad=(np_==BAD_NP and qt=="AAAA" and ts>=SYM)
                if pname=="dns_query_latency_p99_ms":
                    val=3200*random.uniform(0.85,1.05) if bad else 12*random.uniform(0.7,1.3)
                else:
                    val=8200*random.uniform(0.9,1.1) if (np_==BAD_NP and qt=="AAAA") else 1200*random.uniform(0.8,1.2)
                M(pname,ts,round(val,1),{"node_pool":np_,"dns_server":(BAD_DNS if np_==BAD_NP else "10.20.4.10"),
                    "query_type":qt,"response_code":"NOERROR","region":BAD_REGION,"cluster":CLUSTER})
# L7-9 - network (decoys) + kernel/eBPF + IRQ/NUMA
for ts in range(WIN,NOW,STEP):
    for np_ in [BAD_NP,"NP-09"]:
        M("node_nic_mtu",ts,9000.0 if np_==BAD_NP else 1500.0,{"node_pool":np_,"nic":"eth0","cluster":CLUSTER})
for pname,b in [("net_tcp_rtt_ms",0.8),("net_udp_packet_loss_pct",0.01),("net_bandwidth_mbps",240)]:
    for ts in range(WIN,NOW,STEP):
        M(pname,ts,round(b*random.uniform(0.8,1.2),3),{"node_pool":BAD_NP,"cluster":CLUSTER})
for ts in range(WIN,NOW,STEP):
    for qn in range(16):
        numa=0 if qn<8 else 1
        bad=(qn==7 and ts>=IRQ)
        val=2800*random.uniform(0.9,1.05) if bad else random.uniform(0.05,0.4)
        M("kernel_rx_queue_latency_ms",ts,round(val,3),{"node_pool":BAD_NP,"nic_queue":f"RX-{qn}","numa_node":str(numa),"node":"node-np17-8","cluster":CLUSTER})
for ts in range(WIN,NOW,STEP):
    M("kernel_udp_recvmsg_latency_ms",ts,round((2750*random.uniform(0.9,1.05)) if ts>=IRQ else random.uniform(0.1,0.6),3),
        {"node_pool":BAD_NP,"nic_queue":"RX-7","numa_node":"1","cpu":"48","cluster":CLUSTER})
for ts in range(WIN,NOW,STEP):
    M("irq_affinity_numa_mismatch",ts,1.0 if ts>=IRQ else 0.0,
        {"node_pool":BAD_NP,"nic_queue":"RX-7","irq_cpu":"48","irq_numa":"1","queue_mem_numa":"0","node_image_version":BAD_IMG,"cluster":CLUSTER})
for ts in range(WIN,NOW,STEP):
    M("softirq_cpu_usage_percent",ts,round((88*random.uniform(0.9,1.05)) if ts>=IRQ else 12*random.uniform(0.7,1.3),1),
        {"node_pool":BAD_NP,"cpu":"48","numa_node":"1","cluster":CLUSTER})

# ===================== LOGS =====================
for ts in range(SYM,NOW,30):
    pod=random.choice(BAD_PODS)
    L("payment_service_logs",ts,"WARN","payment.client","Payment provider request timeout",{"pod":pod,"provider":"payments.provider.com","node_pool":BAD_NP,"service":"payment-service"})
    L("payment_service_logs",ts+2,"ERROR","payment.retry","Retry attempt 2/3",{"pod":pod,"service":"payment-service","node_pool":BAD_NP})
    L("payment_service_logs",ts+4,"WARN","http.connection",f"Connection acquisition took {random.randint(3800,4600)}ms",{"pod":pod,"service":"payment-service","node_pool":BAD_NP})
for i in range(6):
    ts=SYM+i*300+random.randint(0,120)
    L("payment_service_logs",ts,"WARN","dns.resolver",
      f"DNS resolution exceeded expected latency hostname=payments.provider.com query=AAAA latency={random.randint(3000,3300)}ms",
      {"pod":random.choice(BAD_PODS),"dns_server":BAD_DNS,"query_type":"AAAA","node_pool":BAD_NP,"service":"payment-service"})
for ts in range(SYM,NOW,45):
    L("checkout_service_logs",ts,"WARN","checkout.orchestrator",
      f"Downstream payment call slow ({random.randint(9000,18000)}ms) region=Region-B currency=INR cart_items={random.randint(13,22)}",
      {"service":"checkout-service","payment_method":"CARD","currency":"INR"})
for ts in range(IRQ,NOW,60):
    L("kernel_logs",ts,"WARN","kernel.net",
      f"RX queue 7 processing latency high ({random.randint(2600,2900)}ms) cpu=48 numa=1 (queue memory numa=0 cross-NUMA)",
      {"node_pool":BAD_NP,"node":"node-np17-8","nic_queue":"RX-7"})
L("infra_change_logs",IRQ,"INFO","infra.automation","Node pool NP-17 rolled to node image 2026.06.18 (IRQ balancing configuration applied)",
  {"change_type":"node_image_rollout","node_pool":BAD_NP,"node_image_version":BAD_IMG,"prev_image":GOOD_IMG,"service":"infra"})
L("infra_change_logs",IRQ+5,"WARN","infra.automation","IRQ affinity set: RX-7 -> CPU48 (NUMA node 1); NIC queue memory on NUMA node 0",
  {"change_type":"irq_affinity","node_pool":BAD_NP,"nic_queue":"RX-7","irq_cpu":"48","service":"infra"})
L("infra_change_logs",NOW-14*24*3600,"INFO","deploy.app","Deployed payment-risk feature: extra risk check for CARD+INR+cart_items>12 (adds device-intelligence + risk provider DNS lookups)",
  {"change_type":"app_deploy","service":"checkout-service","feature":"payment_risk_check","checkout_version":CHK_VER})

# ===================== TRACES (spans) =====================
def build_trace(slow):
    tid=hexid(32); t0=random.randint(SYM if slow else WIN, NOW-60)
    s_ck=hexid(16); dur_ck=18000 if slow else 200
    S(tid,s_ck,None,"checkout-service","POST /checkout",2,t0,dur_ck,
      {"payment_method":"CARD","currency":("INR" if slow else "USD"),
       "cart_items":str(random.randint(13,20) if slow else random.randint(1,10)),
       "checkout_version":CHK_VER,"http.route":"/checkout"})
    for svc,nm,dur in [("pricing-service","GET /price",22),("inventory-service","GET /stock",40),
                       ("promotion-service","GET /promo",18),("order-service","POST /order",45)]:
        S(tid,hexid(16),s_ck,svc,nm,2,t0,dur,{"peer.service":svc})
    s_pay_cl=hexid(16); s_pay=hexid(16); dur_pay=17800 if slow else 70
    pod=random.choice(BAD_PODS) if slow else "payment-pod-107"
    pay_attr={"pod":pod,"node_pool":(BAD_NP if slow else "NP-09"),"availability_zone":(BAD_AZ if slow else "A1"),
              "version":PAY_VER,"peer.service":"payment-service"}
    S(tid,s_pay_cl,s_ck,"checkout-service","payment call",3,t0,dur_pay,{"peer.service":"payment-service"})
    S(tid,s_pay,s_pay_cl,"payment-service","POST /pay",2,t0,dur_pay,pay_attr)
    S(tid,hexid(16),s_pay,"token-service","token lookup",2,t0,30,{"peer.service":"token-service"})
    S(tid,hexid(16),s_pay,"fraud-service","fraud check",2,t0,45,{"peer.service":"fraud-service"})
    prov_dur=17000 if slow else 60
    S(tid,hexid(16),s_pay,"payment-provider","HTTP POST payments.provider.com",3,t0,prov_dur,
      {"peer.service":"payment-provider","net.peer.name":"payments.provider.com","dns.query_type":"AAAA",
       "dns.server":BAD_DNS,"pod":pod,"node_pool":(BAD_NP if slow else "NP-09")})
for _ in range(24): build_trace(True)
for _ in range(60): build_trace(False)

# ===================== EMIT SQL =====================
def q(s):  return "'" + str(s).replace("'","''") + "'"
def jb(d): return "'" + json.dumps(d).replace("'","''") + "'::jsonb"
def tsf(e):return "to_timestamp(%d)" % int(e)
def batched(header, valrows, chunk=500):
    for i in range(0, len(valrows), chunk):
        print(header); print(",\n".join(valrows[i:i+chunk]) + ";")

print("-- E-commerce cross-NUMA RCA scenario dump (generated by dump_scenario_postgres.sh)")
if SCHEMA != "public":
    print(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};")
print(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.otel_metrics (
  tenant_id text NOT NULL, ts timestamptz NOT NULL, metric_name text NOT NULL,
  value double precision, labels jsonb);
CREATE INDEX IF NOT EXISTS otel_metrics_tenant_metric_ts ON {SCHEMA}.otel_metrics (tenant_id, metric_name, ts);
CREATE TABLE IF NOT EXISTS {SCHEMA}.otel_logs (
  tenant_id text NOT NULL, ts timestamptz NOT NULL, stream text NOT NULL,
  level text, logger text, message text, attributes jsonb);
CREATE INDEX IF NOT EXISTS otel_logs_tenant_stream_ts ON {SCHEMA}.otel_logs (tenant_id, stream, ts);
CREATE TABLE IF NOT EXISTS {SCHEMA}.otel_spans (
  tenant_id text NOT NULL, trace_id text NOT NULL, span_id text NOT NULL, parent_span_id text,
  service_name text, span_name text, span_kind text,
  start_time timestamptz, end_time timestamptz, duration_ms double precision, attributes jsonb);
CREATE INDEX IF NOT EXISTS otel_spans_tenant_trace ON {SCHEMA}.otel_spans (tenant_id, trace_id);
CREATE INDEX IF NOT EXISTS otel_spans_tenant_svc_ts ON {SCHEMA}.otel_spans (tenant_id, service_name, start_time);""")

print("BEGIN;")
for tid in TENANTS:
    T=q(tid)
    if TRUNC:
        print(f"DELETE FROM {SCHEMA}.otel_metrics WHERE tenant_id={T};")
        print(f"DELETE FROM {SCHEMA}.otel_logs    WHERE tenant_id={T};")
        print(f"DELETE FROM {SCHEMA}.otel_spans   WHERE tenant_id={T};")
    mv=[f"({T},{tsf(ts)},{q(name)},{val},{jb(lb)})" for (name,ts,val,lb) in metrics]
    batched(f"INSERT INTO {SCHEMA}.otel_metrics (tenant_id,ts,metric_name,value,labels) VALUES", mv)
    lv=[f"({T},{tsf(ts)},{q(st)},{q(lvl)},{q(lg)},{q(msg)},{jb(a)})" for (st,ts,lvl,lg,msg,a) in logs]
    batched(f"INSERT INTO {SCHEMA}.otel_logs (tenant_id,ts,stream,level,logger,message,attributes) VALUES", lv)
    sv=[f"({T},{q(trid)},{q(sid)},{('NULL' if parent is None else q(parent))},{q(svc)},{q(nm)},{q(kd)},{tsf(sts)},{tsf(ets)},{round(dur,3)},{jb(a)})"
        for (trid,sid,parent,svc,nm,kd,sts,ets,dur,a) in spans]
    batched(f"INSERT INTO {SCHEMA}.otel_spans (tenant_id,trace_id,span_id,parent_span_id,service_name,span_name,span_kind,start_time,end_time,duration_ms,attributes) VALUES", sv)
print("COMMIT;")

import sys
sys.stderr.write(f"   generated per-tenant rows -> metrics:{len(metrics)} logs:{len(logs)} spans:{len(spans)}  x {len(TENANTS)} tenant(s)\n")
PYEOF

echo ">> Loading into PostgreSQL ${USER}@${HOST}:${PORT}/${DB} ..."
PGPASSWORD="$PASSWORD" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -q -f "$SQL_FILE"

echo ">> Done. Row counts per tenant:"
PGPASSWORD="$PASSWORD" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -P pager=off -c \
"SELECT tenant_id, 'metrics' AS kind, count(*) FROM ${SCHEMA}.otel_metrics GROUP BY tenant_id
 UNION ALL SELECT tenant_id, 'logs',   count(*) FROM ${SCHEMA}.otel_logs   GROUP BY tenant_id
 UNION ALL SELECT tenant_id, 'spans',  count(*) FROM ${SCHEMA}.otel_spans  GROUP BY tenant_id
 ORDER BY tenant_id, kind;"
