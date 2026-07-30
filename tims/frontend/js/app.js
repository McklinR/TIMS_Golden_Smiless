/* ============================================================
   TIMS frontend — vanilla JS SPA talking to the FastAPI backend.
   No build step: open via the FastAPI-served index, or any static
   server, as long as API_BASE points at the backend.
   ============================================================ */
const API_BASE = ""; // same-origin (FastAPI serves this frontend)

const state = {
  token: localStorage.getItem("tims_token") || null,
  role: localStorage.getItem("tims_role") || null,
  fullName: localStorage.getItem("tims_name") || null,
  clientsCache: null,
  transportersCache: null,
  currentView: "dashboard",
};

// ---------------------------------------------------------------
// API helper
// ---------------------------------------------------------------
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  let payload;
  if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = new URLSearchParams(form).toString();
  } else if (body) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  if (res.status === 401) {
    logout();
    throw new Error("Session expired - please sign in again.");
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const detail = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = "toast"; }, 3200);
}

// ---------------------------------------------------------------
// Auth
// ---------------------------------------------------------------
function logout() {
  state.token = null; state.role = null; state.fullName = null;
  localStorage.removeItem("tims_token");
  localStorage.removeItem("tims_role");
  localStorage.removeItem("tims_name");
  document.getElementById("app-shell").classList.add("hidden");
  document.getElementById("login-screen").classList.remove("hidden");
}

async function login(username, password) {
  const data = await api("/auth/login", { method: "POST", form: { username, password } });
  state.token = data.access_token;
  state.role = data.role;
  state.fullName = data.full_name;
  localStorage.setItem("tims_token", state.token);
  localStorage.setItem("tims_role", state.role);
  localStorage.setItem("tims_name", state.fullName);
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    await login(username, password);
    enterApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

document.getElementById("logout-btn").addEventListener("click", logout);

// ---------------------------------------------------------------
// Shell / nav
// ---------------------------------------------------------------
function enterApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  document.getElementById("rail-user-name").textContent = state.fullName || "—";
  document.getElementById("rail-user-role").textContent = state.role || "—";

  document.querySelectorAll(".rail-item").forEach(btn => {
    const roles = btn.dataset.roles;
    if (roles && !roles.split(",").includes(state.role)) {
      btn.style.display = "none";
    } else {
      btn.style.display = "";
    }
  });

  navigate("dashboard");
}

document.getElementById("rail-nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".rail-item");
  if (!btn) return;
  navigate(btn.dataset.view);
});

const VIEW_TITLES = {
  dashboard: "Dashboard", bookings: "Bookings", loading: "Loading (Weighbridge)",
  tracking: "Route Tracking", offloading: "Offloading (Terminal)", accounts: "Accounts",
  admin: "Admin — Clients & Transporters",
};

async function navigate(view) {
  state.currentView = view;
  document.querySelectorAll(".rail-item").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  document.getElementById("view-title").textContent = VIEW_TITLES[view] || view;
  const container = document.getElementById("view");
  container.innerHTML = `<div class="empty-state">Loading…</div>`;
  try {
    const renderers = {
      dashboard: renderDashboard, bookings: renderBookings, loading: renderLoading,
      tracking: renderTracking, offloading: renderOffloading, accounts: renderAccounts,
      admin: renderAdmin,
    };
    await (renderers[view] || renderDashboard)(container);
  } catch (err) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtMoney(n) { return n == null ? "—" : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function fmtTonnes(n) { return n == null ? "—" : `${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })} t`; }
function fmtDate(d) { if (!d) return "—"; const dt = new Date(d); return dt.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
function pill(status) { return `<span class="pill pill-${status}">${status.replace(/_/g, " ")}</span>`; }

// clock
setInterval(() => {
  const el = document.getElementById("clock");
  if (el) el.textContent = new Date().toLocaleString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}, 1000);

// ---------------------------------------------------------------
// Cached lookups
// ---------------------------------------------------------------
async function getClients() {
  if (state.clientsCache) return state.clientsCache;
  try { state.clientsCache = await api("/clients"); } catch (e) { state.clientsCache = []; }
  return state.clientsCache;
}
async function getTransporters() {
  if (state.transportersCache) return state.transportersCache;
  state.transportersCache = await api("/transporters");
  return state.transportersCache;
}

// =================================================================
// DASHBOARD
// =================================================================
async function renderDashboard(container) {
  const s = await api("/dashboard/summary");
  const cards = [
    { label: "Active Bookings", value: s.active_bookings, accent: "var(--ore-copper)" },
    { label: "Awaiting Loading", value: s.booked_awaiting_loading, accent: "var(--signal-teal)" },
    { label: "In Transit", value: s.in_transit, accent: "var(--ore-copper)" },
    { label: "Expired (7d)", value: s.expired_this_week, accent: "var(--alert-red)" },
    { label: "Loaded Tonnage", value: fmtTonnes(s.total_loaded_tonnage), accent: "var(--signal-teal)" },
    { label: "Offloaded Tonnage", value: fmtTonnes(s.total_offloaded_tonnage), accent: "var(--signal-teal)" },
    { label: "Outstanding Liability", value: fmtMoney(s.outstanding_balance_liability), accent: "var(--alert-amber)" },
  ];
  if (s.total_gross_margin != null) {
    cards.push({ label: "Gross Broker Margin", value: fmtMoney(s.total_gross_margin), accent: "var(--ore-copper)" });
    cards.push({ label: "Penalty Margin Recovery", value: fmtMoney(s.total_penalty_recovery), accent: "var(--ore-copper)" });
  }

  const bookings = await api("/bookings");
  const recent = bookings.slice(0, 6);

  container.innerHTML = `
    <div class="kpi-grid">
      ${cards.map(c => `
        <div class="kpi-card" style="--accent:${c.accent}">
          <div class="kpi-label">${c.label}</div>
          <div class="kpi-value">${c.value}</div>
        </div>`).join("")}
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3>Recent Bookings</h3>
        <span class="panel-sub">Latest 6 · 48h weighbridge SLA auto-expires stale bookings</span>
      </div>
      ${recent.length ? `
      <table>
        <thead><tr><th>Horse Reg</th><th>Driver</th><th>Origin</th><th>Status</th><th>Loaded</th><th>Booked</th></tr></thead>
        <tbody>
          ${recent.map(b => `
            <tr>
              <td class="mono">${escapeHtml(b.horse_registration)}</td>
              <td>${escapeHtml(b.driver_name)}</td>
              <td>${escapeHtml(b.origin || "—")}</td>
              <td>${pill(b.status)}</td>
              <td>${fmtTonnes(b.loaded_tonnage)}</td>
              <td class="mono">${fmtDate(b.booking_date)}</td>
            </tr>`).join("")}
        </tbody>
      </table>` : `<div class="empty-state">No bookings yet.</div>`}
    </div>
  `;
}

// =================================================================
// BOOKINGS
// =================================================================
function routeTrack(status) {
  const stages = ["BOOKED", "LOADED", "IN_TRANSIT", "OFFLOADED"];
  if (status === "EXPIRED" || status === "CANCELLED") {
    return `<div class="empty-state" style="padding:6px 0;text-align:left;color:var(--alert-red)">${status}</div>`;
  }
  const idx = stages.indexOf(status);
  return `<div class="route-track">
    ${stages.map((st, i) => `
      ${i > 0 ? `<div class="route-line ${i <= idx ? "done" : ""}"></div>` : ""}
      <div class="route-node ${i < idx ? "done" : i === idx ? "current" : ""}">
        <span class="dot"></span><span>${st.replace("_", " ")}</span>
      </div>`).join("")}
  </div>`;
}

async function renderBookings(container) {
  const canCreate = ["ADMIN", "BOOKING"].includes(state.role);
  const [bookings, clients, transporters] = await Promise.all([
    api("/bookings"), canCreate ? getClients() : [], canCreate ? getTransporters() : [],
  ]);

  container.innerHTML = `
    ${canCreate ? `
    <div class="panel">
      <div class="panel-head"><h3>New Booking</h3><span class="panel-sub">Source a truck against a client/transporter pair</span></div>
      <form id="booking-form" class="form-grid">
        <label class="field-label">Horse Registration<input class="field-input" name="horse_registration" required></label>
        <label class="field-label">Trailer 1 Reg<input class="field-input" name="trailer1_registration"></label>
        <label class="field-label">Trailer 2 Reg<input class="field-input" name="trailer2_registration"></label>
        <label class="field-label">Driver Name<input class="field-input" name="driver_name" required></label>
        <label class="field-label">Passport No<input class="field-input" name="passport_number"></label>
        <label class="field-label">Origin
          <select class="field-input" name="origin">
            ${["Lalapanzi", "Mapanzure", "NETA", "Mberegwa", "Shurugwi", "Zvishavane"].map(o => `<option>${o}</option>`).join("")}
          </select>
        </label>
        <label class="field-label">ETA<input class="field-input" type="datetime-local" name="eta"></label>
        <label class="field-label">Client
          <select class="field-input" name="client_id" required>
            ${clients.map(c => `<option value="${c.id}">${escapeHtml(c.name)} ($${c.default_client_rate}/t)</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Transporter
          <select class="field-input" name="transporter_id" required>
            ${transporters.map(t => `<option value="${t.id}">${escapeHtml(t.name)} ($${t.default_transporter_rate}/t)</option>`).join("")}
          </select>
        </label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-primary" type="submit">Create Booking</button>
        </div>
      </form>
    </div>` : ""}

    <div class="panel">
      <div class="panel-head"><h3>All Bookings</h3><span class="panel-sub">${bookings.length} total</span></div>
      ${bookings.length ? bookings.map(b => `
        <div style="padding:14px 0;border-bottom:1px solid var(--hairline)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
            <div>
              <strong class="mono">${escapeHtml(b.horse_registration)}</strong>
              &nbsp;·&nbsp; ${escapeHtml(b.driver_name)} &nbsp;·&nbsp; <span style="color:var(--text-faint)">${escapeHtml(b.origin || "—")}</span>
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              ${b.gross_broker_margin != null ? `<span class="mono" style="color:var(--ore-copper);font-size:12px">margin ${fmtMoney(b.gross_broker_margin)}</span>` : ""}
              ${pill(b.status)}
              ${pill(b.payment_status)}
            </div>
          </div>
          ${routeTrack(b.status)}
          <div style="margin-top:8px;font-size:11.5px;color:var(--text-faint)">
            Loaded ${fmtTonnes(b.loaded_tonnage)} · Deposit ${fmtMoney(b.deposit_amount)} · Balance ${fmtMoney(b.balance_amount)} · Booked ${fmtDate(b.booking_date)}
          </div>
        </div>
      `).join("") : `<div class="empty-state">No bookings yet — create one above.</div>`}
    </div>
  `;

  const form = document.getElementById("booking-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.client_id = Number(payload.client_id);
      payload.transporter_id = Number(payload.transporter_id);
      if (!payload.eta) delete payload.eta; else payload.eta = new Date(payload.eta).toISOString();
      try {
        await api("/bookings", { method: "POST", body: payload });
        toast("Booking created.");
        navigate("bookings");
      } catch (err) { toast(err.message, true); }
    });
  }
}

// =================================================================
// LOADING (weighbridge capture)
// =================================================================
async function renderLoading(container) {
  const bookings = (await api("/bookings")).filter(b => b.status === "BOOKED");

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Capture Loading Slip</h3><span class="panel-sub">Weighbridge ticket — transitions booking to LOADED</span></div>
      ${bookings.length ? `
      <form id="loading-form" class="form-grid">
        <label class="field-label">Booking
          <select class="field-input" name="booking_id" required>
            ${bookings.map(b => `<option value="${b.id}">${escapeHtml(b.horse_registration)} — ${escapeHtml(b.driver_name)} (${escapeHtml(b.origin || "")})</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Ticket No<input class="field-input" name="ticket_no" required placeholder="WB-0001"></label>
        <label class="field-label">Time In<input class="field-input" name="time_in" placeholder="08:15"></label>
        <label class="field-label">Time Out<input class="field-input" name="time_out" placeholder="09:40"></label>
        <label class="field-label">1st Mass / Tare (t)<input class="field-input" type="number" step="0.01" name="tare_mass" required></label>
        <label class="field-label">2nd Mass / Gross (t)<input class="field-input" type="number" step="0.01" name="gross_mass" required></label>
        <label class="field-label">Operator Signature<input class="field-input" name="operator_signature"></label>
        <label class="field-label">Driver Signature<input class="field-input" name="driver_signature"></label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-primary" type="submit">Log Loading Slip</button>
        </div>
      </form>` : `<div class="empty-state">No bookings currently awaiting loading.</div>`}
    </div>
  `;

  const form = document.getElementById("loading-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      payload.tare_mass = Number(payload.tare_mass);
      payload.gross_mass = Number(payload.gross_mass);
      try {
        const slip = await api("/loading-slips", { method: "POST", body: payload });
        toast(`Loading slip logged — net ${slip.net_mass} t.`);
        navigate("loading");
      } catch (err) { toast(err.message, true); }
    });
  }
}

// =================================================================
// TRACKING (call log with NLP quick-flags)
// =================================================================
const FLAG_COLORS = {
  BREAKDOWN: "var(--alert-red)", BORDER: "var(--alert-amber)", DELAYED: "var(--alert-amber)",
  ON_ROUTE: "var(--signal-teal)", OFFLOADING: "var(--signal-teal)", ARRIVED: "var(--signal-teal)",
};

async function renderTracking(container) {
  const [bookings, logs] = await Promise.all([
    api("/bookings"), api("/tracking-logs?limit=30"),
  ]);
  const active = bookings.filter(b => ["LOADED", "IN_TRANSIT"].includes(b.status));

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Log a Check-in Call</h3><span class="panel-sub">Type the note naturally — status &amp; location are auto-detected</span></div>
      ${active.length ? `
      <form id="tracking-form" class="form-grid">
        <label class="field-label">Booking
          <select class="field-input" name="booking_id" required>
            ${active.map(b => `<option value="${b.id}">${escapeHtml(b.horse_registration)} — ${escapeHtml(b.driver_name)}</option>`).join("")}
          </select>
        </label>
        <label class="field-label" style="grid-column: span 2">Call note
          <input class="field-input" name="raw_note" required placeholder="e.g. driver says delayed at Beitbridge border, clearing customs">
        </label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-teal" type="submit">Log Call</button>
        </div>
      </form>` : `<div class="empty-state">No trucks currently in transit to track.</div>`}
    </div>

    <div class="panel">
      <div class="panel-head"><h3>Recent Check-ins</h3><span class="panel-sub">${logs.length} logged</span></div>
      ${logs.length ? logs.map(l => `
        <div class="tracklog-item">
          <div class="tracklog-flag">
            ${l.status_flag ? `<span class="pill" style="background:transparent;border:1px solid ${FLAG_COLORS[l.status_flag] || "var(--hairline)"};color:${FLAG_COLORS[l.status_flag] || "var(--text-muted)"}">${l.status_flag.replace("_", " ")}</span>` : `<span class="pill" style="background:transparent;border:1px solid var(--hairline);color:var(--text-faint)">NOTE</span>`}
          </div>
          <div>
            <div class="tracklog-note">${escapeHtml(l.raw_note)}</div>
            <div class="tracklog-meta">booking #${l.booking_id}${l.location_guess ? ` · location: ${escapeHtml(l.location_guess)}` : ""} · ${fmtDate(l.logged_at)}</div>
          </div>
        </div>
      `).join("") : `<div class="empty-state">No check-ins logged yet.</div>`}
    </div>
  `;

  const form = document.getElementById("tracking-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      try {
        const log = await api("/tracking-logs", { method: "POST", body: payload });
        toast(`Logged${log.status_flag ? ` — flagged ${log.status_flag}` : ""}.`);
        navigate("tracking");
      } catch (err) { toast(err.message, true); }
    });
  }
}

// =================================================================
// OFFLOADING (terminal capture, shrinkage)
// =================================================================
async function renderOffloading(container) {
  const bookings = (await api("/bookings")).filter(b => ["LOADED", "IN_TRANSIT"].includes(b.status));

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Capture Offloading Slip</h3><span class="panel-sub">Terminal weighbridge — computes shrinkage &amp; split penalty automatically</span></div>
      ${bookings.length ? `
      <form id="offload-form" class="form-grid">
        <label class="field-label">Booking
          <select class="field-input" name="booking_id" required>
            ${bookings.map(b => `<option value="${b.id}">${escapeHtml(b.horse_registration)} — loaded ${fmtTonnes(b.loaded_tonnage)}</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Destination
          <select class="field-input" name="destination">
            ${["Costco", "Grindrod", "Vayela"].map(d => `<option>${d}</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Transaction No<input class="field-input" name="transaction_no"></label>
        <label class="field-label">Pre-Advice No<input class="field-input" name="pre_advice_no"></label>
        <label class="field-label">Nett Weight Received (t)<input class="field-input" type="number" step="0.01" name="nett_weight_received" required></label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-primary" type="submit">Log Offloading</button>
        </div>
      </form>` : `<div class="empty-state">No trucks currently awaiting offloading capture.</div>`}
    </div>
  `;

  const form = document.getElementById("offload-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      payload.nett_weight_received = Number(payload.nett_weight_received);
      try {
        const off = await api("/offloading", { method: "POST", body: payload });
        toast(off.shrinkage_tonnes > 0
          ? `Captured — shrinkage ${off.shrinkage_tonnes} t detected.`
          : "Captured — no shrinkage.");
        navigate("offloading");
      } catch (err) { toast(err.message, true); }
    });
  }
}

// =================================================================
// ACCOUNTS (Connie's workflow: deposit / balance / mark paid)
// =================================================================
async function renderAccounts(container) {
  const bookings = await api("/bookings");
  const relevant = bookings.filter(b => b.status !== "BOOKED" && b.status !== "CANCELLED");

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Payment Pipeline</h3><span class="panel-sub">80% deposit on loading · 20% balance (shrinkage-adjusted) on clean offload</span></div>
      ${relevant.length ? `
      <table>
        <thead><tr><th>Horse Reg</th><th>Status</th><th>Payment</th><th>Deposit</th><th>Balance</th><th>Action</th></tr></thead>
        <tbody>
          ${relevant.map(b => `
            <tr>
              <td class="mono">${escapeHtml(b.horse_registration)}</td>
              <td>${pill(b.status)}</td>
              <td>${pill(b.payment_status)}</td>
              <td class="mono">${fmtMoney(b.deposit_amount)}</td>
              <td class="mono">${fmtMoney(b.balance_amount)}</td>
              <td>${accountAction(b)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>` : `<div class="empty-state">Nothing in the payment pipeline yet.</div>`}
    </div>
  `;

  container.querySelectorAll("[data-pay-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const { payAction, bookingId } = btn.dataset;
      btn.disabled = true;
      try {
        await api(`/bookings/${bookingId}/${payAction}`, { method: "POST" });
        toast("Updated.");
        navigate("accounts");
      } catch (err) { toast(err.message, true); btn.disabled = false; }
    });
  });
}

function accountAction(b) {
  if (b.payment_status === "NONE" && ["LOADED", "IN_TRANSIT"].includes(b.status)) {
    return `<button class="btn btn-secondary btn-sm" data-pay-action="pay-deposit" data-booking-id="${b.id}">Release 80% Deposit</button>`;
  }
  if (b.payment_status === "DEPOSIT_PAID" && b.status === "OFFLOADED") {
    return `<button class="btn btn-secondary btn-sm" data-pay-action="invoice-balance" data-booking-id="${b.id}">Invoice 20% Balance</button>`;
  }
  if (b.payment_status === "BALANCE_INVOICED") {
    return `<button class="btn btn-teal btn-sm" data-pay-action="mark-fully-paid" data-booking-id="${b.id}">Mark Fully Paid</button>`;
  }
  if (b.payment_status === "FULLY_PAID") return `<span style="color:var(--text-faint);font-size:12px">Settled</span>`;
  return `<span style="color:var(--text-faint);font-size:12px">—</span>`;
}

// =================================================================
// ADMIN (clients & transporters — confidential rate data)
// =================================================================
async function renderAdmin(container) {
  const [clients, transporters] = await Promise.all([getClients(), getTransporters()]);

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Clients</h3><span class="panel-sub">Confidential — admin only</span></div>
      <table>
        <thead><tr><th>Name</th><th>Contact</th><th>Client Rate</th><th>Penalty Rate</th></tr></thead>
        <tbody>
          ${clients.map(c => `<tr><td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.contact_name || "—")}</td><td class="mono">$${c.default_client_rate}/t</td><td class="mono">$${c.default_penalty_rate}/t</td></tr>`).join("")}
        </tbody>
      </table>
      <form id="client-form" class="form-grid" style="margin-top:16px">
        <label class="field-label">Name<input class="field-input" name="name" required></label>
        <label class="field-label">Contact Name<input class="field-input" name="contact_name"></label>
        <label class="field-label">Contact Phone<input class="field-input" name="contact_phone"></label>
        <label class="field-label">Client Rate ($/t)<input class="field-input" type="number" step="0.01" name="default_client_rate" required></label>
        <label class="field-label">Penalty Rate ($/lost t)<input class="field-input" type="number" step="0.01" name="default_penalty_rate" required></label>
        <div class="form-actions" style="grid-column:1/-1"><button class="btn btn-primary btn-sm" type="submit">Add Client</button></div>
      </form>
    </div>

    <div class="panel">
      <div class="panel-head"><h3>Transporters</h3><span class="panel-sub">Truck operators</span></div>
      <table>
        <thead><tr><th>Name</th><th>Contact</th><th>Transporter Rate</th><th>Penalty Rate</th></tr></thead>
        <tbody>
          ${transporters.map(t => `<tr><td>${escapeHtml(t.name)}</td><td>${escapeHtml(t.contact_name || "—")}</td><td class="mono">$${t.default_transporter_rate}/t</td><td class="mono">$${t.default_penalty_rate}/t</td></tr>`).join("")}
        </tbody>
      </table>
      <form id="transporter-form" class="form-grid" style="margin-top:16px">
        <label class="field-label">Name<input class="field-input" name="name" required></label>
        <label class="field-label">Contact Name<input class="field-input" name="contact_name"></label>
        <label class="field-label">Contact Phone<input class="field-input" name="contact_phone"></label>
        <label class="field-label">Transporter Rate ($/t)<input class="field-input" type="number" step="0.01" name="default_transporter_rate" required></label>
        <label class="field-label">Penalty Rate ($/lost t)<input class="field-input" type="number" step="0.01" name="default_penalty_rate" required></label>
        <div class="form-actions" style="grid-column:1/-1"><button class="btn btn-primary btn-sm" type="submit">Add Transporter</button></div>
      </form>
    </div>
  `;

  document.getElementById("client-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = Object.fromEntries(new FormData(e.target).entries());
    payload.default_client_rate = Number(payload.default_client_rate);
    payload.default_penalty_rate = Number(payload.default_penalty_rate);
    try {
      await api("/clients", { method: "POST", body: payload });
      state.clientsCache = null;
      toast("Client added.");
      navigate("admin");
    } catch (err) { toast(err.message, true); }
  });

  document.getElementById("transporter-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = Object.fromEntries(new FormData(e.target).entries());
    payload.default_transporter_rate = Number(payload.default_transporter_rate);
    payload.default_penalty_rate = Number(payload.default_penalty_rate);
    try {
      await api("/transporters", { method: "POST", body: payload });
      state.transportersCache = null;
      toast("Transporter added.");
      navigate("admin");
    } catch (err) { toast(err.message, true); }
  });
}

// ---------------------------------------------------------------
// Boot
// ---------------------------------------------------------------
(async function boot() {
  if (state.token) {
    try {
      await api("/auth/me");
      enterApp();
      return;
    } catch (e) { /* fall through to login */ }
  }
  document.getElementById("login-screen").classList.remove("hidden");
})();
