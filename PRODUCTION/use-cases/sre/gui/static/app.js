let CATALOG = [];

async function loadScenarios() {
  const r = await fetch("/api/scenarios");
  const data = await r.json();
  CATALOG = data.tenants || [];
  const tSel = document.getElementById("tenant");
  tSel.innerHTML = "";
  CATALOG.forEach(t => {
    const o = document.createElement("option");
    o.value = t.tenant_id; o.textContent = t.display_name;
    tSel.appendChild(o);
  });
  tSel.onchange = fillScenarios;
  fillScenarios();
}

function fillScenarios() {
  const tid = document.getElementById("tenant").value;
  const t = CATALOG.find(x => x.tenant_id === tid);
  const sSel = document.getElementById("scenario");
  sSel.innerHTML = "";
  (t?.scenarios || []).forEach(s => {
    const o = document.createElement("option");
    o.value = s.scenario_id; o.textContent = s.scenario_id;
    o.dataset.alarm = s.alarm;
    sSel.appendChild(o);
  });
  showAlarm();
  sSel.onchange = showAlarm;
}

function showAlarm() {
  const sSel = document.getElementById("scenario");
  const opt = sSel.selectedOptions[0];
  document.getElementById("alarm").textContent = opt ? "alarm: " + opt.dataset.alarm : "";
}

function resetBoard() {
  ["candidate", "investigating", "confirmed", "rejected"].forEach(l =>
    document.getElementById("lane-" + l).innerHTML = "");
  document.getElementById("thoughts").innerHTML = "";
  document.getElementById("conclusion-panel").hidden = true;
  document.getElementById("remediation-panel").hidden = true;
}

function addThought(text) {
  const li = document.createElement("li");
  li.textContent = text;
  document.getElementById("thoughts").appendChild(li);
}

function renderBoard(result) {
  // place each hypothesis card in its status lane
  (result.hypotheses || []).forEach(h => {
    const lane = document.getElementById("lane-" + (h.status || "candidate"))
      || document.getElementById("lane-candidate");
    const card = document.createElement("div");
    card.className = "card " + (h.status || "");
    const reason = h.reason ? `<div class="reason">${escapeHtml(h.reason)}</div>` : "";
    card.innerHTML = `<div class="hid">${h.id || ""}</div>`
      + `<div class="stmt">${escapeHtml(h.statement || "")}</div>${reason}`;
    lane.appendChild(card);
  });

  const c = result.conclusion || {};
  if (c.root_cause) {
    document.getElementById("conclusion-panel").hidden = false;
    const conf = (c.confidence || "").toLowerCase();
    const badge = document.getElementById("confidence");
    badge.textContent = conf || "—"; badge.className = "badge " + conf;
    document.getElementById("root-cause").textContent = c.root_cause;
    const tl = document.getElementById("timeline"); tl.innerHTML = "";
    (c.timeline || []).forEach(step => {
      const li = document.createElement("li"); li.textContent = step; tl.appendChild(li);
    });
  }

  const rem = result.remediation || {};
  const remText = rem.proposal || c.remediation || "";
  if (remText) {
    document.getElementById("remediation-panel").hidden = false;
    document.getElementById("remediation").textContent = remText;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

async function investigate() {
  const btn = document.getElementById("run");
  const status = document.getElementById("status");
  btn.disabled = true; resetBoard();
  const tenant_id = document.getElementById("tenant").value;
  const scenario_id = document.getElementById("scenario").value;
  const alarm = document.getElementById("scenario").selectedOptions[0]?.dataset.alarm;

  const resp = await fetch("/api/investigate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id, scenario_id, alarm }),
  });
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const p of parts) {
      const line = p.trim();
      if (!line.startsWith("data:")) continue;
      const evt = JSON.parse(line.slice(5).trim());
      handleEvent(evt, status);
    }
  }
  btn.disabled = false;
}

function handleEvent(evt, status) {
  switch (evt.type) {
    case "start": status.textContent = "investigating…"; break;
    case "status": status.textContent = evt.text; break;
    case "thought": addThought(evt.text); break;
    case "result": renderBoard(evt.result); status.textContent = "done"; break;
    case "error": status.textContent = "error"; addThought("⚠️ " + evt.text); break;
    case "done": break;
  }
}

document.getElementById("run").onclick = investigate;
loadScenarios();
