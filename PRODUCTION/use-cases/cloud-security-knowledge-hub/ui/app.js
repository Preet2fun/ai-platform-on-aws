/* Cloud Security Knowledge Hub — minimal chat SPA.
 *
 * Auth: Cognito Hosted UI (OAuth2 authorization-code + PKCE), no client secret. On return,
 * we exchange the code for tokens and use the id_token (JWT) as the API Authorization header.
 * Query: POST {question} to the /query API; render the grounded answer + citations.
 *
 * Pure vanilla JS (no build step). All config values are public (config.js).
 */
(function () {
  "use strict";
  const cfg = window.CSHUB_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  const chat = $("chat");

  // ---------- PKCE helpers ----------
  function b64url(bytes) {
    return btoa(String.fromCharCode(...new Uint8Array(bytes)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  async function sha256(str) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  }
  function randomVerifier() {
    const a = new Uint8Array(32); crypto.getRandomValues(a); return b64url(a);
  }

  // ---------- token storage ----------
  const store = {
    get id() { return sessionStorage.getItem("cshub_id_token"); },
    set id(v) { v ? sessionStorage.setItem("cshub_id_token", v) : sessionStorage.removeItem("cshub_id_token"); },
    get email() { return sessionStorage.getItem("cshub_email"); },
    set email(v) { v ? sessionStorage.setItem("cshub_email", v) : sessionStorage.removeItem("cshub_email"); },
  };

  async function login() {
    const verifier = randomVerifier();
    sessionStorage.setItem("cshub_pkce", verifier);
    const challenge = b64url(await sha256(verifier));
    const u = new URL(cfg.cognitoDomain + "/oauth2/authorize");
    u.searchParams.set("client_id", cfg.userPoolClientId);
    u.searchParams.set("response_type", "code");
    u.searchParams.set("scope", "openid email profile");
    u.searchParams.set("redirect_uri", cfg.redirectUri);
    u.searchParams.set("code_challenge", challenge);
    u.searchParams.set("code_challenge_method", "S256");
    window.location.assign(u.toString());
  }

  function logout() {
    store.id = null; store.email = null;
    const u = new URL(cfg.cognitoDomain + "/logout");
    u.searchParams.set("client_id", cfg.userPoolClientId);
    u.searchParams.set("logout_uri", cfg.redirectUri);
    window.location.assign(u.toString());
  }

  async function exchangeCode(code) {
    const verifier = sessionStorage.getItem("cshub_pkce");
    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: cfg.userPoolClientId,
      code, redirect_uri: cfg.redirectUri, code_verifier: verifier || "",
    });
    const resp = await fetch(cfg.cognitoDomain + "/oauth2/token", {
      method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body,
    });
    if (!resp.ok) throw new Error("token exchange failed");
    const tok = await resp.json();
    store.id = tok.id_token;
    try {
      const claims = JSON.parse(atob(tok.id_token.split(".")[1]));
      store.email = claims.email || "";
    } catch (_) {}
    // clean the ?code= from the URL
    window.history.replaceState({}, "", cfg.redirectUri);
  }

  // ---------- chat rendering ----------
  function bubble(role, html) {
    const d = document.createElement("div");
    d.className = "bubble " + role;
    d.innerHTML = html;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    return d;
  }
  function esc(s) { return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  function renderAnswer(data) {
    let html = esc(data.answer).replace(/\n/g, "<br>");
    if (Array.isArray(data.citations) && data.citations.length) {
      const items = data.citations
        .map((c) => `<li>[${c.n}] ${esc(c.source || c.doc_id)}</li>`).join("");
      html += `<div class="cites"><b>Sources</b><ul>${items}</ul></div>`;
    }
    if (data.latency_ms) html += `<div class="meta muted small">${data.retrieved} passages · ${data.latency_ms} ms</div>`;
    bubble("assistant", html);
  }

  async function ask(question) {
    bubble("user", esc(question));
    const pending = bubble("assistant", "<span class='muted'>Searching the knowledge base…</span>");
    try {
      const resp = await fetch(cfg.apiEndpoint, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: store.id || "" },
        body: JSON.stringify({ question }),
      });
      pending.remove();
      if (resp.status === 401) { bubble("assistant", "Please sign in first."); return; }
      const data = await resp.json();
      if (!resp.ok) { bubble("assistant", esc(data.error || "Something went wrong.")); return; }
      renderAnswer(data);
    } catch (e) {
      pending.remove();
      bubble("assistant", "Network error. Please try again.");
    }
  }

  // ---------- auth UI state ----------
  function refreshAuthUi() {
    const signedIn = !!store.id;
    $("loginBtn").hidden = signedIn;
    $("logoutBtn").hidden = !signedIn;
    $("user").textContent = signedIn ? (store.email || "signed in") : "";
    $("askBtn").disabled = !signedIn;
    $("hint").textContent = signedIn ? "" : "Sign in to ask questions.";
  }

  // ---------- boot ----------
  async function boot() {
    $("loginBtn").addEventListener("click", login);
    $("logoutBtn").addEventListener("click", logout);
    $("askForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = $("question").value.trim();
      if (q && store.id) { ask(q); $("question").value = ""; }
    });

    const params = new URLSearchParams(window.location.search);
    if (params.get("code")) {
      try { await exchangeCode(params.get("code")); } catch (_) {}
    }
    refreshAuthUi();
  }

  boot();
})();
