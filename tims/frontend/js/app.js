/* ============================================================
   TIMS frontend — vanilla JS SPA talking to the FastAPI backend.
   No build step: open via the FastAPI-served index, or any static
   server, as long as API_BASE points at the backend.
   ============================================================ */
let API_BASE = "";
let apiBaseResolved = false;

async function resolveApiBase() {
  if (apiBaseResolved) return API_BASE;

  const candidates = [];
  if (typeof window !== "undefined" && window.location) {
    if (window.location.origin) candidates.push(window.location.origin);
    if (window.location.protocol) {
      candidates.push(`${window.location.protocol}//127.0.0.1:8000`);
      candidates.push(`${window.location.protocol}//localhost:8000`);
      candidates.push(`${window.location.protocol}//127.0.0.1:8080`);
      candidates.push(`${window.location.protocol}//localhost:8080`);
    }
  }
  candidates.push("http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:8080", "http://localhost:8080");

  const uniqueCandidates = [...new Set(candidates.filter(Boolean))];
  for (const base of uniqueCandidates) {
    try {
      const res = await fetch(`${base}/api/health`, { method: "GET", cache: "no-store" });
      if (res.ok) {
        API_BASE = base;
        apiBaseResolved = true;
        return API_BASE;
      }
    } catch (e) {
      // try the next candidate
    }
  }

  API_BASE = window.location.origin || "";
  apiBaseResolved = true;
  return API_BASE;
}

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
  const base = await resolveApiBase();
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
  let res;
  try {
    res = await fetch(`${base}${path}`, { method, headers, body: payload });
  } catch (err) {
    console.error("API request failed", { path, err });
    throw new Error("Could not reach the server. Please make sure the backend is running locally and refresh the page.");
  }
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
  const errorEl = document.getElementById("login-error");
  const submitBtn = document.querySelector("#login-form button[type='submit']");
  errorEl.textContent = "";
  if (submitBtn) submitBtn.disabled = true;

  try {
    const data = await api("/api/auth/login", { method: "POST", form: { username, password } });
    state.token = data.access_token;
    state.role = data.role;
    state.fullName = data.full_name;
    localStorage.setItem("tims_token", state.token);
    localStorage.setItem("tims_role", state.role);
    localStorage.setItem("tims_name", state.fullName);
    return;
  } catch (err) {
    console.error("Login failed", err);
    errorEl.textContent = err.message || "Unable to sign in right now.";
    throw err;
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

// ---------------------------------------------------------------
// Shell / nav
// ---------------------------------------------------------------
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "Signing in…";
  try {
    await login(username, password);
    enterApp();
  } catch (err) {
    // error already shown in the form
  }
});

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

document.getElementById("logout-btn").addEventListener("click", () => {
  logout();
  toast("Signed out successfully.");
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

function safeStatus(status) {
  return String(status || "").replace(/_/g, " ");
}

function setFormMessage(form, message, kind = "success") {
  if (!form) return;
  let el = form.querySelector(".form-message");
  if (!el) {
    el = document.createElement("div");
    el.className = "form-message";
    el.setAttribute("aria-live", "polite");
    form.appendChild(el);
  }
  el.textContent = message;
  el.dataset.kind = kind;
}

function clearFormMessage(form) {
  if (!form) return;
  const el = form.querySelector(".form-message");
  if (el) {
    el.textContent = "";
    el.dataset.kind = "";
  }
}

function bookingLookupMaps(bookings, clients = [], transporters = []) {
  const clientMap = new Map(clients.map(client => [String(client.id), client]));
  const transporterMap = new Map(transporters.map(transporter => [String(transporter.id), transporter]));
  const bookingMap = new Map(bookings.map(booking => [String(booking.id), booking]));
  return { clientMap, transporterMap, bookingMap };
}

function bookingSummaryCards(bookings) {
  const counts = bookings.reduce((acc, booking) => {
    const key = booking.status || "UNKNOWN";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const summary = [
    { label: "Booked", value: counts.BOOKED || 0, accent: "var(--signal-teal)" },
    { label: "Loaded", value: counts.LOADED || 0, accent: "var(--ore-copper)" },
    { label: "In Transit", value: counts.IN_TRANSIT || 0, accent: "var(--signal-teal)" },
    { label: "Offloaded", value: counts.OFFLOADED || 0, accent: "var(--signal-teal)" },
    { label: "Expired", value: counts.EXPIRED || 0, accent: "var(--alert-red)" },
    { label: "Cancelled", value: counts.CANCELLED || 0, accent: "var(--text-faint)" },
  ];
  return `
    <div class="kpi-grid compact">
      ${summary.map(item => `
        <div class="kpi-card" style="--accent:${item.accent}">
          <div class="kpi-label">${item.label}</div>
          <div class="kpi-value">${item.value}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function bookingCard(booking, clientMap, transporterMap, canCancel = false) {
  const client = clientMap.get(String(booking.client_id));
  const transporter = transporterMap.get(String(booking.transporter_id));
  const canCancelAction = canCancel && ["BOOKED", "EXPIRED"].includes(booking.status);
  return `
    <article class="record-card">
      <div class="record-card-head">
        <div>
          <div class="record-title mono">${escapeHtml(booking.horse_registration)}</div>
          <div class="record-sub">${escapeHtml(booking.driver_name)} · ${escapeHtml(booking.origin || "No origin set")}</div>
        </div>
        <div class="record-badges">
          ${pill(booking.status)}
          ${pill(booking.payment_status)}
        </div>
      </div>
      <div class="record-meta-grid">
        <div><span>Client</span><strong>${escapeHtml(client?.name || `Client #${booking.client_id}`)}</strong></div>
        <div><span>Client Rate</span><strong>${fmtMoney(booking.client_rate)}/t</strong></div>
        <div><span>Transporter</span><strong>${escapeHtml(transporter?.name || `Transporter #${booking.transporter_id}`)}</strong></div>
        <div><span>Booked</span><strong class="mono">${fmtDate(booking.booking_date)}</strong></div>
        <div><span>ETA</span><strong class="mono">${fmtDate(booking.eta)}</strong></div>
      </div>
      <div class="record-track-wrap">${routeTrack(booking.status)}</div>
      <div class="record-footer">
        <div class="record-kpis">
          <span>Loaded ${fmtTonnes(booking.loaded_tonnage)}</span>
          <span>Deposit ${fmtMoney(booking.deposit_amount)}</span>
          <span>Balance ${fmtMoney(booking.balance_amount)}</span>
          ${booking.gross_broker_margin != null ? `<span>Margin ${fmtMoney(booking.gross_broker_margin)}</span>` : ""}
        </div>
        ${canCancelAction ? `<button class="btn btn-sm btn-danger" data-booking-cancel data-booking-id="${booking.id}">Cancel booking</button>` : ""}
      </div>
    </article>
  `;
}

function workflowEmpty(title, guidance) {
  return `
    <div class="empty-state empty-state-guide">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(guidance)}</span>
    </div>
  `;
}

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
  const { clientMap, transporterMap } = bookingLookupMaps(bookings, clients, transporters);
  const orderedBookings = [...bookings].sort((left, right) => new Date(right.booking_date) - new Date(left.booking_date));
  const activeCount = bookings.filter(booking => ["BOOKED", "LOADED", "IN_TRANSIT"].includes(booking.status)).length;
  const cancellableCount = bookings.filter(booking => ["BOOKED", "EXPIRED"].includes(booking.status)).length;

  container.innerHTML = `
    ${bookingSummaryCards(bookings)}
    ${canCreate ? `
    <div class="panel">
      <div class="panel-head"><h3>New Booking</h3><span class="panel-sub">Source a truck against a client/transporter pair</span></div>
      <form id="booking-form" class="form-grid">
        <label class="field-label">Horse Registration<input class="field-input" name="horse_registration" required placeholder="AFH1234"></label>
        <label class="field-label">Trailer 1 Reg<input class="field-input" name="trailer1_registration" placeholder="AFH1234T1"></label>
        <label class="field-label">Trailer 2 Reg<input class="field-input" name="trailer2_registration" placeholder="AFH1234T2"></label>
        <label class="field-label">Driver Name<input class="field-input" name="driver_name" required placeholder="Tendai Moyo"></label>
        <label class="field-label">Passport No<input class="field-input" name="passport_number" placeholder="ZW1234567"></label>
        <label class="field-label">Origin
          <select class="field-input" name="origin">
            ${["Lalapanzi", "Mapanzure", "NETA", "Mberegwa", "Shurugwi", "Zvishavane"].map(o => `<option>${o}</option>`).join("")}
          </select>
        </label>
        <label class="field-label">ETA<input class="field-input" type="datetime-local" name="eta"></label>
        <label class="field-label">Client
          <select class="field-input" name="client_id" required>
            <option value="">Select client</option>
            ${clients.map(c => `<option value="${c.id}">${escapeHtml(c.name)} ($${c.current_client_rate ?? c.default_client_rate}/t)</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Transporter
          <select class="field-input" name="transporter_id" required>
            <option value="">Select transporter</option>
            ${transporters.map(t => `<option value="${t.id}">${escapeHtml(t.name)} ($${t.default_transporter_rate}/t)</option>`).join("")}
          </select>
        </label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-primary" type="submit">Create Booking</button>
        </div>
      </form>
    </div>` : ""}

    <div class="panel">
      <div class="panel-head"><h3>All Bookings</h3><span class="panel-sub">${bookings.length} total · ${activeCount} active · ${cancellableCount} cancellable</span></div>
      ${orderedBookings.length ? `
        <div class="record-stack">
          ${orderedBookings.map(booking => bookingCard(booking, clientMap, transporterMap, canCreate)).join("")}
        </div>
      ` : workflowEmpty("No bookings yet", "Create the first dispatch using the booking form above. Real demo clients and transporters appear in the dropdowns once seeded.")}
    </div>
  `;

  const form = document.getElementById("booking-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!form.reportValidity()) {
        setFormMessage(form, "Complete the required booking fields.", "error");
        return;
      }
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.client_id = Number(payload.client_id);
      payload.transporter_id = Number(payload.transporter_id);
      if (!payload.eta) delete payload.eta; else payload.eta = new Date(payload.eta).toISOString();
      try {
        clearFormMessage(form);
        await api("/bookings", { method: "POST", body: payload });
        setFormMessage(form, "Booking created successfully.");
        toast("Booking created.");
        navigate("bookings");
      } catch (err) {
        setFormMessage(form, err.message, "error");
        toast(err.message, true);
      }
    });
  }

  container.querySelectorAll("[data-booking-cancel]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const bookingId = btn.dataset.bookingId;
      if (!window.confirm("Cancel this booking?")) return;
      btn.disabled = true;
      try {
        await api(`/bookings/${bookingId}/cancel`, { method: "POST" });
        toast("Booking cancelled.");
        navigate("bookings");
      } catch (err) {
        btn.disabled = false;
        toast(err.message, true);
      }
    });
  });
}

// =================================================================
// LOADING (weighbridge capture)
// =================================================================
async function renderLoading(container) {
  const bookings = await api("/bookings");
  const awaiting = bookings.filter(booking => booking.status === "BOOKED");
  const completed = bookings.filter(booking => booking.loaded_tonnage != null);
  const loadRecords = await Promise.all(completed.map(async booking => {
    try {
      return { booking, slip: await api(`/loading-slips/${booking.id}`) };
    } catch (err) {
      return { booking, slip: null };
    }
  }));

  container.innerHTML = `
    <div class="kpi-grid compact">
      <div class="kpi-card" style="--accent:var(--ore-copper)">
        <div class="kpi-label">Awaiting Weighbridge</div>
        <div class="kpi-value">${awaiting.length}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--signal-teal)">
        <div class="kpi-label">Captured Loads</div>
        <div class="kpi-value">${loadRecords.length}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--signal-teal)">
        <div class="kpi-label">Total Loaded Tonnes</div>
        <div class="kpi-value">${fmtTonnes(loadRecords.reduce((sum, item) => sum + (item.booking.loaded_tonnage || 0), 0))}</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>Capture Loading Slip</h3><span class="panel-sub">Weighbridge ticket — transitions booking to LOADED</span></div>
      ${awaiting.length ? `
      <form id="loading-form" class="form-grid">
        <label class="field-label">Booking
          <select class="field-input" name="booking_id" required>
            ${awaiting.map(b => `<option value="${b.id}">${escapeHtml(b.horse_registration)} — ${escapeHtml(b.driver_name)} (${escapeHtml(b.origin || "")})</option>`).join("")}
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

    <div class="panel">
      <div class="panel-head"><h3>Completed Loading Records</h3><span class="panel-sub">${loadRecords.length} slips captured</span></div>
      ${loadRecords.length ? `
        <div class="record-stack">
          ${loadRecords.map(({ booking, slip }) => `
            <article class="record-card">
              <div class="record-card-head">
                <div>
                  <div class="record-title mono">${escapeHtml(booking.horse_registration)}</div>
                  <div class="record-sub">${escapeHtml(booking.driver_name)} · ticket ${escapeHtml(slip?.ticket_no || "Pending")}</div>
                </div>
                <div class="record-badges">${pill(booking.status)}</div>
              </div>
              <div class="record-meta-grid">
                <div><span>Loaded mass</span><strong>${fmtTonnes(booking.loaded_tonnage)}</strong></div>
                <div><span>Tare</span><strong>${slip ? fmtTonnes(slip.tare_mass) : "—"}</strong></div>
                <div><span>Gross</span><strong>${slip ? fmtTonnes(slip.gross_mass) : "—"}</strong></div>
                <div><span>Origin</span><strong>${escapeHtml(slip?.location || booking.origin || "—")}</strong></div>
              </div>
              <div class="record-footer">
                <div class="record-kpis">
                  <span>Deposit ${fmtMoney(booking.deposit_amount)}</span>
                  <span>Balance ${fmtMoney(booking.balance_amount)}</span>
                  <span>Booked ${fmtDate(booking.booking_date)}</span>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      ` : workflowEmpty("No loading slips captured yet", "Use the form above to capture the first weighbridge slip. Once booked trucks are loaded, they move into the tracking and accounts queues.")}
    </div>
  `;

  const form = document.getElementById("loading-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!form.reportValidity()) {
        setFormMessage(form, "Complete the required loading fields.", "error");
        return;
      }
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      payload.tare_mass = Number(payload.tare_mass);
      payload.gross_mass = Number(payload.gross_mass);
      if (payload.gross_mass <= payload.tare_mass) {
        setFormMessage(form, "Gross mass must be greater than tare mass.", "error");
        return;
      }
      try {
        clearFormMessage(form);
        const slip = await api("/loading-slips", { method: "POST", body: payload });
        setFormMessage(form, `Loading slip ${slip.ticket_no} logged successfully.`);
        toast(`Loading slip logged — net ${slip.net_mass} t.`);
        navigate("loading");
      } catch (err) {
        setFormMessage(form, err.message, "error");
        toast(err.message, true);
      }
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
  const latestLogs = new Map();
  logs.forEach(log => {
    if (!latestLogs.has(log.booking_id)) latestLogs.set(log.booking_id, log);
  });
  const activeCount = active.length;

  container.innerHTML = `
    <div class="kpi-grid compact">
      <div class="kpi-card" style="--accent:var(--signal-teal)">
        <div class="kpi-label">Active Trips</div>
        <div class="kpi-value">${activeCount}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--ore-copper)">
        <div class="kpi-label">Recent Notes</div>
        <div class="kpi-value">${logs.length}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--alert-amber)">
        <div class="kpi-label">Tracking Flags</div>
        <div class="kpi-value">${logs.filter(log => log.status_flag).length}</div>
      </div>
    </div>
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
      <div class="panel-head"><h3>Active Route Board</h3><span class="panel-sub">Latest live locations and statuses</span></div>
      ${active.length ? `
        <div class="record-stack">
          ${active.map(booking => {
    const latest = latestLogs.get(booking.id);
    return `
              <article class="record-card">
                <div class="record-card-head">
                  <div>
                    <div class="record-title mono">${escapeHtml(booking.horse_registration)}</div>
                    <div class="record-sub">${escapeHtml(booking.driver_name)} · ${escapeHtml(booking.origin || "Unknown origin")}</div>
                  </div>
                  <div class="record-badges">
                    ${pill(booking.status)}
                    ${booking.tracking_status ? `<span class="pill pill-${booking.tracking_status}">${safeStatus(booking.tracking_status)}</span>` : ""}
                  </div>
                </div>
                <div class="record-meta-grid">
                  <div><span>Current location</span><strong>${escapeHtml(booking.location_status || booking.origin || "Awaiting update")}</strong></div>
                  <div><span>Latest note</span><strong>${escapeHtml(latest?.raw_note || "No tracking note yet")}</strong></div>
                  <div><span>Last update</span><strong class="mono">${fmtDate(booking.tracking_timestamp || latest?.logged_at)}</strong></div>
                  <div><span>Route stage</span><strong>${escapeHtml(booking.tracking_status || "Untracked")}</strong></div>
                </div>
                ${routeTrack(booking.status)}
              </article>
            `;
  }).join("")}
        </div>
      ` : workflowEmpty("No active trucks to track", "Once a truck is loaded or in transit, it appears here with the latest location and note history.")}
    </div>

    <div class="panel">
      <div class="panel-head"><h3>Recent Check-ins</h3><span class="panel-sub">${logs.length} logged</span></div>
      ${logs.length ? `
        <div class="record-stack">
          ${logs.map(l => `
            <article class="tracklog-item">
              <div class="tracklog-flag">
                ${l.status_flag ? `<span class="pill" style="background:transparent;border:1px solid ${FLAG_COLORS[l.status_flag] || "var(--hairline)"};color:${FLAG_COLORS[l.status_flag] || "var(--text-muted)"}">${safeStatus(l.status_flag)}</span>` : `<span class="pill" style="background:transparent;border:1px solid var(--hairline);color:var(--text-faint)">NOTE</span>`}
              </div>
              <div class="tracklog-body">
                <div class="tracklog-note">${escapeHtml(l.raw_note)}</div>
                <div class="tracklog-meta">booking #${l.booking_id}${l.location_guess ? ` · location: ${escapeHtml(l.location_guess)}` : ""} · ${fmtDate(l.logged_at)}</div>
              </div>
            </article>
          `).join("")}
        </div>
      ` : `<div class="empty-state">No check-ins logged yet.</div>`}
    </div>
  `;

  const form = document.getElementById("tracking-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!form.reportValidity()) {
        setFormMessage(form, "Enter a tracking note before submitting.", "error");
        return;
      }
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      try {
        clearFormMessage(form);
        const log = await api("/tracking-logs", { method: "POST", body: payload });
        setFormMessage(form, `Tracking note logged${log.status_flag ? ` and flagged ${log.status_flag}` : ""}.`);
        toast(`Logged${log.status_flag ? ` — flagged ${log.status_flag}` : ""}.`);
        navigate("tracking");
      } catch (err) {
        setFormMessage(form, err.message, "error");
        toast(err.message, true);
      }
    });
  }
}

// =================================================================
// OFFLOADING (terminal capture, shrinkage)
// =================================================================
async function renderOffloading(container) {
  const bookings = await api("/bookings");
  const active = bookings.filter(b => ["LOADED", "IN_TRANSIT"].includes(b.status));
  const completed = bookings.filter(b => b.status === "OFFLOADED");
  const { bookingMap } = bookingLookupMaps(bookings, [], []);
  const offloadRecords = await Promise.all(completed.map(async booking => {
    try {
      return { booking, offload: await api(`/offloading/${booking.id}`) };
    } catch (err) {
      return { booking, offload: null };
    }
  }));
  const totalShrinkage = offloadRecords.reduce((sum, item) => sum + (item.offload?.shrinkage_tonnes || 0), 0);
  const totalRecovery = offloadRecords.reduce((sum, item) => sum + (item.offload?.penalty_margin_recovery || 0), 0);

  container.innerHTML = `
    <div class="kpi-grid compact">
      <div class="kpi-card" style="--accent:var(--signal-teal)">
        <div class="kpi-label">Awaiting Offload</div>
        <div class="kpi-value">${active.length}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--ore-copper)">
        <div class="kpi-label">Completed Offloads</div>
        <div class="kpi-value">${offloadRecords.length}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--alert-amber)">
        <div class="kpi-label">Total Shrinkage</div>
        <div class="kpi-value">${fmtTonnes(totalShrinkage)}</div>
      </div>
      <div class="kpi-card" style="--accent:var(--signal-teal)">
        <div class="kpi-label">Penalty Recovery</div>
        <div class="kpi-value">${fmtMoney(totalRecovery)}</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>Capture Offloading Slip</h3><span class="panel-sub">Terminal weighbridge — computes shrinkage &amp; split penalty automatically</span></div>
      ${active.length ? `
      <form id="offload-form" class="form-grid">
        <label class="field-label">Booking
          <select class="field-input" name="booking_id" required>
            ${active.map(b => `<option value="${b.id}">${escapeHtml(b.horse_registration)} — loaded ${fmtTonnes(b.loaded_tonnage)}</option>`).join("")}
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
        <label class="field-label">First Weight<input class="field-input" type="number" step="0.01" name="first_weight"></label>
        <label class="field-label">Second Weight<input class="field-input" type="number" step="0.01" name="second_weight"></label>
        <label class="field-label">Tare Weight<input class="field-input" type="number" step="0.01" name="tare_weight"></label>
        <div class="form-actions" style="grid-column:1/-1">
          <button class="btn btn-primary" type="submit">Log Offloading</button>
        </div>
      </form>` : `<div class="empty-state">No trucks currently awaiting offloading capture.</div>`}
    </div>

    <div class="panel">
      <div class="panel-head"><h3>Completed Offload Records</h3><span class="panel-sub">${offloadRecords.length} completed receipts</span></div>
      ${offloadRecords.length ? `
        <div class="record-stack">
          ${offloadRecords.map(({ booking, offload }) => `
            <article class="record-card">
              <div class="record-card-head">
                <div>
                  <div class="record-title mono">${escapeHtml(booking.horse_registration)}</div>
                  <div class="record-sub">${escapeHtml(offload?.destination || "Unknown destination")} · transaction ${escapeHtml(offload?.transaction_no || "Pending")}</div>
                </div>
                <div class="record-badges">${pill(booking.status)}</div>
              </div>
              <div class="record-meta-grid">
                <div><span>Received</span><strong>${fmtTonnes(offload?.nett_weight_received)}</strong></div>
                <div><span>Shrinkage</span><strong>${fmtTonnes(offload?.shrinkage_tonnes)}</strong></div>
                <div><span>Client charge</span><strong>${fmtMoney(offload?.client_penalty_charge)}</strong></div>
                <div><span>Transporter charge</span><strong>${fmtMoney(offload?.transporter_penalty_charge)}</strong></div>
              </div>
              <div class="record-footer">
                <div class="record-kpis">
                  <span>Recovery ${fmtMoney(offload?.penalty_margin_recovery)}</span>
                  <span>Deposit ${fmtMoney(booking.deposit_amount)}</span>
                  <span>Balance ${fmtMoney(booking.balance_amount)}</span>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      ` : workflowEmpty("No offloading records captured yet", "Capture a terminal slip after loading so the destination, shrinkage, and financial outcomes are recorded here.")}
    </div>
  `;

  const form = document.getElementById("offload-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!form.reportValidity()) {
        setFormMessage(form, "Complete the required offloading fields.", "error");
        return;
      }
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.booking_id = Number(payload.booking_id);
      payload.nett_weight_received = Number(payload.nett_weight_received);
      ["first_weight", "second_weight", "tare_weight"].forEach(field => {
        if (payload[field] === "" || payload[field] == null) {
          delete payload[field];
        } else {
          payload[field] = Number(payload[field]);
        }
      });
      const booking = bookingMap.get(String(payload.booking_id));
      if (booking) {
        payload.driver_name = booking.driver_name;
        payload.transporter_name = booking.transporter_name || undefined;
        payload.horse_registration = booking.horse_registration;
        payload.trailer1 = booking.trailer1_registration || undefined;
        payload.trailer2 = booking.trailer2_registration || undefined;
      }
      try {
        clearFormMessage(form);
        const off = await api("/offloading", { method: "POST", body: payload });
        setFormMessage(form, `Offloading captured at ${off.destination || "the terminal"}.`);
        toast(off.shrinkage_tonnes > 0
          ? `Captured — shrinkage ${off.shrinkage_tonnes} t detected.`
          : "Captured — no shrinkage.");
        navigate("offloading");
      } catch (err) {
        setFormMessage(form, err.message, "error");
        toast(err.message, true);
      }
    });
  }
}

// =================================================================
// ACCOUNTS (Edina's workflow: deposit / balance / mark paid)
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
  const [clients, transporters, users] = await Promise.all([getClients(), getTransporters(), api("/users")]);

  const onboardingSuggestions = [
    { username: "erick", full_name: "Erick Logistics", role: "ADMIN" },
    { username: "lyn", full_name: "Lyn Operations", role: "TRACKING" },
    { username: "precious", full_name: "Precious Smiles", role: "BOOKING" },
    { username: "edina", full_name: "Edina Finance", role: "ACCOUNTS" },
  ];

  container.innerHTML = `
    <div class="panel">
      <div class="panel-head"><h3>Director onboarding</h3><span class="panel-sub">Add Erick, Lyn, and other team members</span></div>
      <div class="form-grid" style="margin-bottom:16px">
        ${onboardingSuggestions.map(s => `
          <div class="panel" style="padding:12px;display:flex;justify-content:space-between;align-items:center;gap:12px">
            <div>
              <strong>${escapeHtml(s.full_name)}</strong>
              <div style="color:var(--text-faint);font-size:12px">${escapeHtml(s.username)} • ${s.role}</div>
            </div>
            <button class="btn btn-sm btn-secondary" type="button" data-prefill-user='${JSON.stringify(s)}'>Use</button>
          </div>
        `).join("")}
      </div>
      <div class="panel-head"><h3>Users</h3><span class="panel-sub">Director-managed access</span></div>
      <table>
        <thead><tr><th>Username</th><th>Full name</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>
          ${users.map(user => `
            <tr>
              <td>${escapeHtml(user.username)}</td>
              <td>${escapeHtml(user.full_name)}</td>
              <td>
                <select class="field-input" data-user-role-select data-user-id="${user.id}">
                  ${["ADMIN", "BOOKING", "TRACKING", "ACCOUNTS"].map(role => `<option value="${role}" ${user.role === role ? "selected" : ""}>${role}</option>`).join("")}
                </select>
              </td>
              <td>
                <button class="btn btn-sm ${user.is_active ? "btn-secondary" : "btn-teal"}" data-user-toggle data-user-id="${user.id}" data-active="${user.is_active}">
                  ${user.is_active ? "Deactivate" : "Activate"}
                </button>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      <form id="user-form" class="form-grid" style="margin-top:16px">
        <label class="field-label">Username<input class="field-input" name="username" required></label>
        <label class="field-label">Full Name<input class="field-input" name="full_name" required></label>
        <label class="field-label">Password<input class="field-input" type="password" name="password" required></label>
        <label class="field-label">Role
          <select class="field-input" name="role" required>
            <option value="ADMIN">ADMIN</option>
            <option value="BOOKING">BOOKING</option>
            <option value="TRACKING">TRACKING</option>
            <option value="ACCOUNTS">ACCOUNTS</option>
          </select>
        </label>
        <div class="form-actions" style="grid-column:1/-1"><button class="btn btn-primary btn-sm" type="submit">Add User</button></div>
      </form>
    </div>

    <div class="panel">
      <div class="panel-head"><h3>Clients</h3><span class="panel-sub">Confidential — admin only</span></div>
      <table>
        <thead><tr><th>Name</th><th>Contact</th><th>Client Rate</th><th>Penalty Rate</th></tr></thead>
        <tbody>
          ${clients.map(c => `<tr><td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.contact_name || "—")}</td><td class="mono">$${(c.current_client_rate ?? c.default_client_rate)}/t</td><td class="mono">$${(c.current_penalty_rate ?? c.default_penalty_rate)}/t</td></tr>`).join("")}
        </tbody>
      </table>
      <form id="client-rate-form" class="form-grid" style="margin-top:16px">
        <label class="field-label">Client
          <select class="field-input" name="client_id" required>
            ${clients.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("")}
          </select>
        </label>
        <label class="field-label">Client Rate ($/t)<input class="field-input" type="number" step="0.01" name="client_rate" required></label>
        <label class="field-label">Penalty Rate ($/lost t)<input class="field-input" type="number" step="0.01" name="penalty_rate" required></label>
        <label class="field-label">Effective From<input class="field-input" type="datetime-local" name="effective_from"></label>
        <label class="field-label" style="grid-column:1/-1">Notes<input class="field-input" name="notes" placeholder="Contract change, terminal renegotiation, etc."></label>
        <div class="form-actions" style="grid-column:1/-1"><button class="btn btn-secondary btn-sm" type="submit">Add Rate Change</button></div>
      </form>
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

  container.querySelectorAll("[data-prefill-user]").forEach(btn => {
    btn.addEventListener("click", () => {
      const suggestion = JSON.parse(btn.dataset.prefillUser);
      const form = document.getElementById("user-form");
      form.querySelector('input[name="username"]').value = suggestion.username;
      form.querySelector('input[name="full_name"]').value = suggestion.full_name;
      form.querySelector('select[name="role"]').value = suggestion.role;
      form.querySelector('input[name="password"]').focus();
      toast(`Prefilled ${suggestion.full_name}.`);
    });
  });

  document.getElementById("user-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = Object.fromEntries(new FormData(e.target).entries());
    try {
      await api("/users", { method: "POST", body: payload });
      toast("User added.");
      navigate("admin");
    } catch (err) { toast(err.message, true); }
  });

  container.querySelectorAll("[data-user-role-select]").forEach(select => {
    select.addEventListener("change", async () => {
      const userId = select.dataset.userId;
      try {
        await api(`/users/${userId}`, { method: "PATCH", body: { role: select.value } });
        toast("User role updated.");
        navigate("admin");
      } catch (err) { toast(err.message, true); }
    });
  });

  container.querySelectorAll("[data-user-toggle]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const userId = btn.dataset.userId;
      const nextState = btn.dataset.active === "true" ? false : true;
      try {
        await api(`/users/${userId}`, { method: "PATCH", body: { is_active: nextState } });
        toast(nextState ? "User activated." : "User deactivated.");
        navigate("admin");
      } catch (err) { toast(err.message, true); }
    });
  });

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

  document.getElementById("client-rate-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = Object.fromEntries(new FormData(e.target).entries());
    payload.client_id = Number(payload.client_id);
    payload.client_rate = Number(payload.client_rate);
    payload.penalty_rate = Number(payload.penalty_rate);
    if (payload.effective_from) payload.effective_from = new Date(payload.effective_from).toISOString();
    try {
      await api(`/clients/${payload.client_id}/rate-history`, {
        method: "POST",
        body: {
          client_rate: payload.client_rate,
          penalty_rate: payload.penalty_rate,
          effective_from: payload.effective_from,
          notes: payload.notes,
        },
      });
      state.clientsCache = null;
      toast("Client rate updated.");
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
