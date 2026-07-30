# TIMS — Transport Management System
**Golden Smiles Freight and Distribution**
Shop 6L, 148 Chiremba Rd, Queensdale, Harare

A freight brokering platform for multi-vehicle mineral/commodity transport
(chrome ore) from Zimbabwean mines to South African ports/terminals.

## What's built

- **FastAPI + SQLAlchemy backend** (`backend/`) — bookings, loading slips,
  offloading, tracking, accounts, role-based auth, all wired to a SQLite
  database (`tims.db`, created automatically).
- **Vanilla JS + HTML/CSS frontend** (`frontend/`) — dark, dense operational
  dashboard, no build step required. Served directly by FastAPI at `/`.
- **Business logic implemented exactly per spec:**
  - Broker margin = Client Rate − Transporter Rate (per tonne), admin-only visibility.
  - 80% deposit / 20% balance cash-flow split, released by Accounts (Connie)
    at the right lifecycle stage.
  - Split shrinkage penalty: client charges broker (e.g. $200/t), broker
    charges transporter (e.g. $250/t) — the difference is auto-computed as
    protective margin recovery.
  - **48-hour booking expiry rule** — any `BOOKED` truck that hasn't logged a
    loading slip within 48h of its booking date is automatically flagged
    `EXPIRED` the next time any endpoint reads it (no cron needed for the
    demo; see "Production notes" below for a real scheduler).
  - Role-based permissions matching the team: **Admin/Director** (full
    financial visibility), **Erick** (Booking & Loading), **Lyn & Precious**
    (Tracking — with a lightweight offline NLP parser that turns a free-text
    call note like *"driver says delayed at Beitbridge border"* into a
    quick-select status flag + location), **Connie** (Accounts/Invoicing).

## Quick start

```bash
cd tims
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# seed demo users, clients, transporters, and two sample bookings
python -m backend.seed

# run the server (serves both the API and the dashboard UI)
uvicorn backend.main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser.

Interactive API docs (Swagger UI) are at **http://127.0.0.1:8000/docs**.

### Demo logins (seeded)

| Username  | Password    | Role     | Represents                    |
|-----------|-------------|----------|--------------------------------|
| director  | admin123    | ADMIN    | Director — full visibility     |
| erick     | erick123    | BOOKING  | Erick — booking & loading      |
| lyn       | lyn123      | TRACKING | Lyn — route tracking           |
| precious  | precious123 | TRACKING | Precious — route tracking      |
| connie    | connie123   | ACCOUNTS | Connie — invoicing & payables  |

## Project layout

```
tims/
├── backend/
│   ├── main.py            # FastAPI app entrypoint, mounts frontend + routers
│   ├── database.py        # SQLAlchemy engine/session (SQLite by default)
│   ├── models.py          # ORM models + core business logic (margin, expiry, etc.)
│   ├── schemas.py         # Pydantic request/response contracts
│   ├── auth.py            # JWT auth, password hashing, role-based dependencies
│   ├── nlp.py             # Lightweight keyword parser for tracking call notes
│   ├── seed.py            # Demo data seeding script
│   └── routers/
│       ├── auth_router.py     # /auth/login, /auth/me
│       ├── partners.py        # /clients, /transporters
│       ├── bookings.py        # /bookings — create/list/expire/cancel
│       ├── loading.py         # /loading-slips, /bookings/{id}/pay-deposit
│       ├── offloading.py      # /offloading, invoice-balance, mark-fully-paid
│       ├── tracking.py        # /tracking-logs
│       └── dashboard.py       # /dashboard/summary
├── frontend/
│   ├── index.html
│   ├── css/style.css      # Dark "weighbridge control room" design system
│   └── js/app.js          # SPA logic — fetch calls, view rendering, no framework
├── requirements.txt
└── README.md
```

## Editing in VS Code

This is a completely standard FastAPI + vanilla JS project — open the `tims/`
folder in VS Code and everything (Python IntelliSense, debugging via
`uvicorn backend.main:app --reload`, editing the frontend with live reload
via your browser) works out of the box. No Node/npm required for the
frontend since it's plain HTML/CSS/JS.

Recommended VS Code extensions: **Python** (ms-python.python) and
**Pylance** for the backend.

## Extending it

- **New origins/destinations**: `origin`/`destination` are free-text-backed
  dropdowns in the frontend (`frontend/js/app.js`) seeded from the spec's
  list (Lalapanzi, Mapanzure, NETA, Mberegwa, Shurugwi, Zvishavane / Costco,
  Grindrod, Vayela) — just add more strings to those arrays; the backend
  accepts any string.
- **New tracking keywords**: edit `STATUS_KEYWORDS` / `KNOWN_LOCATIONS` in
  `backend/nlp.py`.
- **New roles or permissions**: extend `UserRole` in `backend/models.py` and
  the `require_roles(...)` calls in each router.

## Production notes (before going live)

1. Set a real `TIMS_SECRET_KEY` environment variable (JWT signing key) — the
   default in `backend/auth.py` is for local dev only.
2. Point `TIMS_DATABASE_URL` at Postgres/MySQL instead of SQLite for
   concurrent multi-user access (e.g. `postgresql://user:pass@host/db`).
3. The 48h expiry check currently runs lazily (on read). For a live "EXPIRED"
   badge even with nobody browsing the app, add a scheduled job (e.g. APScheduler
   or a cron hitting a small `/internal/refresh-expiry` endpoint) every few minutes.
4. Add HTTPS termination (e.g. behind Nginx or a managed platform) before
   deploying beyond localhost, since JWTs are sent as Bearer tokens.
5. Consider audit logging (who released which deposit, who invoiced which
   balance) for the Director's audit requirement — currently the DB records
   timestamps but not a full change log.
