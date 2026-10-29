<<<<<<< HEAD
# Fraud-detection
=======
# FraudShield — SQL-based real-time fraud detection & transaction monitoring

FraudShield checks every bank, card and UPI payment **before the money moves**. Each payment is
compared with the account's own history by **nine fraud rules that run inside MySQL** (a stored
procedure). The rules add up to a risk score from 0 to 100:

| Score | Decision | What the customer sees |
|---|---|---|
| 0 – 39 | **Approved** | The payment goes through. |
| 40 – 69 | **Held for review** | The payment is paused; an analyst checks it and the customer is asked “Was this you?” |
| 70 – 100 | **Blocked** | The payment is stopped; the customer is told immediately. |

Its special feature is **OTP Shield**: when someone who looks like a fraudster asks for an OTP
(a new phone, a new payee, a strange city…), **no OTP is created at all**. The customer's own
registered phone is asked “Was this you? YES / NO” instead, so there is nothing a scam caller can
trick them into sharing.

Everything a person sees is in plain English: every decision says *why*, in one sentence per
warning sign.

---

## 1. What you need

| Software | Version | Notes |
|---|---|---|
| Windows 10/11 | — | macOS/Linux work too (use the commands in section 6) |
| MySQL Server | 8.0 | Running on `localhost:3306` (service “MySQL80”) |
| Python | 3.11, 3.12 or 3.13 | Tick **“Add python.exe to PATH”** when installing |
| Node.js | 18 or newer | For the web app |

## 2. Install (one time)

1. Open `backend\.env` in Notepad and check the database settings. `DB_PASSWORD` must be your
   MySQL **root** password. Special characters such as `@` are fine — FraudShield encodes the
   password itself. (If `.env` doesn't exist yet, `setup.bat` creates it from `.env.example`.)
2. Double-click **`backend\setup.bat`**. It:
   - creates a Python virtual environment and installs the packages,
   - creates the databases **`fraud_sql`** and **`fraud_sql_test`** (no `mysql` command needed),
   - builds all tables, indexes, views, triggers and both stored procedures,
   - loads the demo data: 3 staff users, the 9 rules, 200 customers with ~270 accounts,
     60 shops, a watchlist, 90 days of payment history (~27,000 payments), labelled fraud
     stories, and Ravi, the demo customer for OTP Shield,
   - installs the web app's packages.

   It prints the number of rows in every table at the end. Running it again is safe.

## 3. Run

Double-click **`start_all.bat`** (in the project folder). Two windows open — the API on
port 5000 and the web app on port 5173 — and your browser opens **http://localhost:5173**.

| Username | Password | Can do |
|---|---|---|
| `admin` | `Admin@123` | Everything, including managing users |
| `risk` | `Risk@123` | Rules, watchlist, Fraud Lab, evaluation, audit log |
| `analyst` | `Analyst@123` | Dashboard, live monitor, alerts and cases |

Demo bank customer (used automatically by the OTP Shield page): **`ravi.kumar` / `Ravi@123`**.

To stop, close the two server windows.

### Run with Docker instead

```bash
docker compose up --build
```

Then open **http://localhost:8080** (the API is at `http://localhost:8080/api`). Docker runs its
own MySQL inside the Docker network — it never clashes with your local MySQL — and builds the
schema and loads the demo data on first start (about a minute). To choose the Docker MySQL
password, copy `.env.example` (project folder) to `.env` and edit `DOCKER_DB_PASSWORD`.
Stop with `docker compose down` (add `-v` to also delete the Docker database).

## 4. What's where

| Page | What it shows |
|---|---|
| **Landing** (`/`) | Public page: Ravi's OTP-scam story in 5 steps, the 9 protections, how it works |
| **Dashboard** | Payments today / 7 / 30 / 90 days, approved / held / blocked, money protected, decision time, charts |
| **Live Monitor** | New payments slide in within 2 seconds; blocked ones flash red; click any row |
| **Payment details** | “Why was this decision made?” — risk gauge, each warning sign in plain English, the 6-stage pipeline with real timings |
| **Alerts** | Held and blocked payments, most urgent first; assign to yourself |
| **Case** | Evidence, timeline, notes, **Confirm fraud** / **Mark as genuine** |
| **Rules** | Turn rules on/off, change limits and points — the very next payment uses them |
| **Fraud Lab** | One button per fraud story (R1–R9) plus a normal payment; live traffic generator |
| **OTP Shield demo** | Two phones side by side: the fraudster's and Ravi's |
| **Evaluation** | Recall, false alarms, precision, F1, speed and throughput against the targets |
| **Watchlist / Audit log / Users** | Known-bad devices and accounts · who changed what · staff accounts |

## 5. A 5-minute viva demo

1. **Landing page (30 s).** “Every payment is checked before money moves. Normal ones pass, suspicious
   ones are held or blocked, always with a reason in plain English.” Click *Try the live demo* and
   log in as `admin`.
2. **Fraud Lab (1 min).** Press **Normal payment** → Approved, risk 0. Press **Impossible travel (R3)**
   → the card used in Hyderabad and minutes later in Mumbai is caught; point at the sentence the
   database wrote and the decision time in milliseconds. Switch on **Start live traffic**.
3. **Live Monitor (45 s).** Payments slide in every second; blocked ones flash red. Click one →
   **Why was this decision made?**: the gauge, each warning sign, the rules that did *not* fire,
   and the 6 stages with their real timings. “All of this was decided by one stored procedure.”
4. **OTP Shield (1 min 30 s).** On the *Scam attempt* tab: log in on the fraudster's phone (stolen
   password, Delhi), add payee Kumar, send ₹48,000. “Look — no OTP was created. There is nothing to
   share.” Ravi's phone shows *Was this you?* → tap **NO** → payment blocked, phone logged out,
   watchlist updated. Then show *Genuine · new payee*: a real OTP arrives with a clear warning.
5. **Alerts → Case (45 s).** The new HIGH alert is at the top. Open it, add a note, **Confirm fraud**.
6. **Rules (30 s).** Change R2 from 5 to 3 payments — “the very next payment uses it” — then the audit
   log shows who changed it (recorded by a database trigger).
7. **Evaluation (30 s).** Show the last run: recall, false-alarm rate, p95 latency and throughput,
   each with a ✓ against its target.

Useful talking points: rules run **in SQL** (window function `LAG()` for impossible travel,
sliding-window `COUNT()` for velocity, `NOT EXISTS` for new devices); the whole decision is one
**atomic** database transaction; the same `external_ref` sent twice returns the stored decision
(**idempotent**); thresholds live in the `fraud_rules` table, not in code.

## 6. Command reference

From the `backend` folder with the virtual environment active (`venv\Scripts\activate`):

| Command | Does |
|---|---|
| `flask create-db` | Create `fraud_sql` and `fraud_sql_test` if missing |
| `flask db upgrade` | Create/upgrade tables **and** load all SQL objects |
| `flask init-db-objects` | (Re)load indexes, views, triggers and stored procedures |
| `flask show-db-objects` | List procedures, functions, triggers and views |
| `flask seed` | Load demo data (safe to repeat) |
| `flask reset-rules` | Put rule limits and points back to the defaults |
| `flask export-master-data` | Snapshot your database so teammates get it on `flask db upgrade` (see below) |
| `flask load-master-data --replace` | Make this database an exact copy of the snapshot (deletes its rows first) |
| `flask simulate-scenario R3` | Run one fraud story and print the decision |
| `python simulate.py --rate 5 --fraud-ratio 0.03 --minutes 2` | Stream payments to the running API |
| `python evaluate.py` | Evaluate 5,000 labelled payments through the running API |
| `python -m pytest` | Run the test suite (uses `fraud_sql_test`, never touches `fraud_sql`) |
| `python -m pytest --cov=portal` | …with coverage |
| `python app.py` | API with auto-reload (development) |
| `python wsgi.py` | API with Waitress (what `start_backend.bat` runs) |

### Sharing your data with the team

The data in your `fraud_sql` (customers, merchants, watchlist, rule settings, payments, alerts,
cases) travels through git:

1. **You:** `flask export-master-data`, then commit `backend/portal/master_data/` and
   `backend/migrations/versions/` and push. Add `--master-only` to share only reference data
   (no payments, alerts or cases).
2. **Teammates:** `git pull`, then `flask db upgrade`. The new migration loads the snapshot.

Staff passwords, login sessions and the audit log are not shared; staff logins get their passwords
from each person's own `.env`. Loading adds and updates rows by ID, so it is exact on an empty
database. If a teammate's database already has different data, they run
`flask load-master-data --replace` for an exact copy. If two people export at the same time,
`flask db upgrade` reports "multiple heads"; keep the newest snapshot migration and delete the
other.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `Access denied for user 'root'@'localhost'` | `DB_PASSWORD` in `backend\.env` is not your MySQL root password. Type it exactly as it is; don't URL-encode it. |
| `Can't connect to MySQL server on '127.0.0.1'` | Start MySQL: Windows key → *Services* → **MySQL80** → *Start*. Check `DB_PORT` (default 3306). |
| `Port 5000 / 5173 is already in use` | Another program uses it. Close it, or find it with `netstat -ano | findstr :5000` and end that PID in Task Manager. |
| Web app shows “Cannot reach the FraudShield server” | The API window isn't running or crashed — look at its window; start `backend\start_backend.bat`. |
| `'py' is not recognized` / Python not found | Install Python 3.11–3.13 from python.org with “Add to PATH” ticked, then reopen the window. |
| Strange characters (`â‚¹`) in a console window | Cosmetic only. The scripts switch the console to UTF-8; in your own window run `chcp 65001`. |
| OTP Shield says “Too many OTP requests” | Press **Replay story** — it resets Ravi's demo data, including the 5-per-10-minutes OTP limit. |
| I changed rules and want the defaults back | `flask reset-rules` |
| Start completely fresh | In MySQL Workbench: `DROP DATABASE fraud_sql;` then run `setup.bat` again. |

## 8. Decisions made while building

* **Weights tuned from the specification's starting values.** With the original weights a story
  that trips a single rule (for example only R1 = 30 points) stayed under the 40-point hold line,
  so recall was far below 90%. The tuned defaults and before/after numbers are in
  [backend/docs/RULES.md](backend/docs/RULES.md). The original values are kept there for reference.
* **R7 has four settings** (count, from-amount, to-amount, hours), so `fraud_rules` has a `param_4`
  column, and a `param_labels` column so the Rules page can label every setting.
* **Decision bands are stored** in a small `system_settings` table so they can be changed from the
  Rules page; the stored procedure reads them on every payment.
* **Only approved payments update an account's memory.** A blocked attempt does not register the
  fraudster's device as “seen” and does not wake up a dormant account.
* **Impossible travel ignores blocked attempts**, so a stopped fraud attempt in another city does not
  make the real customer's next payment look suspicious.
* **Evaluation cleans up after itself.** It deletes the payments, alerts and other rows it created,
  so measuring never pollutes the dashboard or the alert queue (`--keep` to keep them).
* **Labels in fraud stories:** only the payment a story is designed to catch is labelled fraud; build-up
  payments (the first five small “card testing” payments of R2, the first two structured payments of
  R7) are unlabelled and not counted in the metrics; the genuine customer's own payment in R3 is
  labelled genuine.
* **Live traffic speed.** Real customers don't pay every few seconds, and doing so would correctly
  trigger R2. So each demo customer pays at most once every 150 seconds, which caps normal live
  traffic at about 2 payments per second with 200 customers. Evaluation spreads its payments over the
  last 7 days for the same reason, and measures throughput separately.
* **Extra tables:** `case_notes` (several notes per case), `token_blocklist` (logout),
  `system_settings` (bands) and `daily_stats` (cached daily totals refreshed every 5 minutes).
* **Fonts are bundled** (`@fontsource`), so the app looks right without internet during a viva.

## 9. Project structure

```
fraudshield/
├── backend/            Flask API, SQL engine, seeders, tests, docs
│   ├── portal/sql/     01_indexes · 02_views · 03_triggers · 04_sp_evaluate_transaction · 05_sp_otp_risk_check
│   ├── portal/services fraud_engine · otp_shield · notifier · simulator · evaluator
│   ├── portal/api/     one blueprint per area (14)
│   ├── docs/           API.md · RULES.md · ARCHITECTURE.md
│   └── tests/          rules R1–R9, scoring, OTP Shield, auth/RBAC, atomicity, performance
├── frontend/           React 18 + Vite + Tailwind + Framer Motion + Recharts
├── docker-compose.yml  mysql + backend + frontend (Nginx) → http://localhost:8080
└── start_all.bat       start everything on Windows
```

Further reading: [API reference](backend/docs/API.md) · [The 9 rules](backend/docs/RULES.md) ·
[Architecture](backend/docs/ARCHITECTURE.md).
>>>>>>> 8831528 (Fraude detection)
