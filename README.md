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
   - creates the database **`fraude`** (no `mysql` command needed),
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

The landing page has three entrances — **Bank staff** (the logins above), **Customer app** and
**Fraudster demo** — plus a **split-screen demo**. See section 3a.

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

## 3a. Customer app, fraudster console and split-screen demo

Three separate experiences share one backend and one fraud engine:

| Who | URL | Login | Token kind |
|---|---|---|---|
| Bank staff | `/login` → `/app` | `admin` / `risk` / `analyst` (above) | `staff` |
| Customer (banking app) | `/bank` | `ravi`, `priya`, `suresh`, `lakshmi`, `arjun` — password **`Name@123`** (e.g. `Ravi@123`, `Lakshmi@123`) | `customer` |
| Fraudster (simulation console) | `/attacker` | `hacker1` (Delhi Gang), `hacker2` (Mumbai Crew) — password **`Hacker@123`** | `fraudster` |
| Split screen | `/demo` | log in on each side | — |

Token kinds never cross: a staff token is refused by customer and fraudster endpoints and vice
versa; customers only ever see their own account (ids come from the token, never the request).

**Demo customers.** Ravi (Hyderabad, the OTP Shield customer), Priya (Bengaluru, high spender),
Suresh (Chennai), **Lakshmi (Hyderabad, dormant — no activity for ~7 months)** and Arjun (Pune). Each
has a balance, a trusted phone, a debit card (`CARD-nnnn`), two long-standing payees and 90 days of
everyday payments. hacker1 holds stolen credentials for Ravi (phishing link), Suresh (card skimming),
Lakshmi (SIM swap) and Priya (OTP call); hacker2 for Arjun, Priya, Lakshmi and Suresh. The gang's
mule account (`99887766554433`) is on the watchlist.

**Setup.** `flask db upgrade` creates the new tables (`customer_users`, `fraudster_users`,
`stolen_credentials`, `customer_alerts`, `attack_events`, plus `accounts.held_amount`,
`transactions.funds_status`, `cases.customer_response`) without touching existing data; `flask seed`
(or just `flask seed-demo`) adds the demo logins. Both are safe to run again.
**Between demos:** press **Reset demo** in the fraudster console or run `flask seed-demo --reset` — it
puts the five demo accounts back to their seeded balances and removes their demo payments, alerts,
holds and the watchlist entries those payments created (the seeded mule entry stays).

**Money rules** (`backend/portal/services/funds.py`, applied inside the same database transaction as
the decision):

| Decision / answer | Money |
|---|---|
| APPROVED | debited from the balance |
| REVIEW | reserved in `held_amount` — not paid |
| BLOCKED | nothing moves |
| Customer: **This was me** (password re-entered) | hold released and the payment completed — exactly once |
| Customer: **Not me** | hold released, nothing paid; fraudster's session ended; device, IP and payee watchlisted; staff case marked |

Every money change is a conditional `UPDATE` (e.g. "only if still HELD"), so retries and double
clicks cannot pay twice, and CHECK constraints keep `balance >= 0` and `0 <= held_amount <= balance`.
Customer payments carry an idempotency key, are limited to ₹2,00,000 each and ₹5,00,000 a day, and
are refused (and not saved) without enough available balance. Synthetic traffic — seeded history,
evaluations and the Fraud Lab / live stream — exercises the rules but moves no money.

**How the fraudster console works.** Each button (R1–R9, *Run combined attack*) calls
`POST /api/attacker/attack/<code>`; the server builds the payments for a victim whose credentials that
fraudster holds and sends each one through `fraud_engine.ingest()`, so `sp_evaluate_transaction`
decides and the console shows the bank's real decision, the rules that fired, the reference and what
happened to the money. R9 first asks **OTP Shield** for an OTP exactly as the bank app does. Late-night
and burst patterns use a server-side simulation clock (the payment time is set to 02:15, or a few
minutes apart); the rules are unchanged. Amounts, payees and timing are fixed by the server — the
console is not a free-form attack tool — and it only works while `DEMO_MODE` is on (default on in
development, **off in the production config**).

**Device and location.** The browser keeps a random device id in `localStorage` (one per role), so a
normal window keeps its device and a private/incognito window is a new device. It sends the id and the
chosen demo city as `X-Device-Id` / `X-Demo-City`. They are only inputs to the rules — a device becomes
trusted only after the server verifies the customer — and the network address is never taken from the
client (on localhost a stable demo address is derived from the device id).

**Customer alerts.** The app polls `GET /api/customer/alerts` every 2 seconds; a new held or blocked
payment appears within one poll with a red animated alert and a sound (a visual "sound is blocked —
tap to enable" fallback appears when the browser blocks audio). The one-sentence reason is the fired
rule's own plain-English explanation from `fraud_rules`. Staff see the customer's answer — *Waiting*,
*This was me* or *Not me* — on the Alerts page and the case page.

### Three-minute demo script

Before starting: run `flask seed-demo --reset` (or press **Reset demo**), open `/demo`, log in on the
left as **hacker1 / Hacker@123** and on the right as **lakshmi / Lakshmi@123**; open `/login` in another
tab as **analyst / Analyst@123** on the **Alerts** page.

1. **0:00–0:30 — Three roles.** On the landing page show the three entrances: bank staff, the customer
   app and the fraudster demo. Open the split screen.
2. **0:30–1:00 — The fraudster.** Left side: hacker1 "Delhi Gang", the SIMULATION ONLY banner, and the
   stolen credentials — Lakshmi's via SIM swap (note: dormant). Passwords are never shown.
3. **1:00–1:30 — The attack.** Press **R8 · Sleeping account**. The console shows the bank's real
   decision: **REVIEW**, rule **R8** ("No activity for ~210 days, then suddenly ₹22,000"), the reference,
   and "money on hold".
4. **1:30–2:00 — The customer's phone.** Right side: within two seconds Lakshmi's phone shows the red
   alert with a sound — *On hold: ₹22,000 — was this you?* — and the home screen shows ₹22,000 on hold.
5. **2:00–2:30 — "Not me".** Tap **Not me** → *Report*. The hold is released (available balance back to
   ₹2,60,000, nothing paid); the fraudster console is logged out ("The bank ended your session"); the
   device and IP are on the watchlist.
6. **2:30–3:00 — Staff view.** In the analyst tab the alert shows **Customer: Not me** and money
   "hold released"; open the case to show the badge and the audit timeline. Back on the phone, Home
   shows balance ₹2,60,000 and ₹0 on hold.

Alternatives: **R9 · Phishing + OTP call** on Ravi shows OTP Shield refusing to create an OTP and the
transfer being **BLOCKED**; **Run combined attack** plays cloned card → card testing → net-banking
takeover to the mule account. To show *This was me*, attack again (after a reset) and confirm with the
customer's password: the held money is paid once and the phone becomes trusted.

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
| **Customer app** (`/bank`) | Phone-style banking app: Home (balance, on hold), Pay, Alerts (bell + unread badge), History, Profile |
| **Fraudster demo** (`/attacker`) | Simulation console: stolen credentials, one button per rule R1–R9, combined attack, live results |
| **Split screen** (`/demo`) | Fraudster console and the victim's phone side by side |

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
| `flask create-db` | Create the `fraude` database if missing |
| `flask db upgrade` | Create/upgrade tables **and** load all SQL objects |
| `flask init-db-objects` | (Re)load indexes, views, triggers and stored procedures |
| `flask show-db-objects` | List procedures, functions, triggers and views |
| `flask seed` | Load demo data (safe to repeat) |
| `flask reset-rules` | Put rule limits and points back to the defaults (`--spec-weights`: the specification's Table 4.4 weights) |
| `flask benchmark-indexes` | Load test through the running API with and without the composite indexes |
| `flask verify-audit` | Re-compute the audit log's hash chain (tamper check) |
| `flask export-ddl` | Rewrite `docs/schema.sql`, the CREATE TABLE script |
| `flask evaluation-report` | Evaluate against Table 3.1 through the running API and write `docs/EVALUATION.md` plus the labelled data set `docs/evaluation_dataset.csv` (`--skip-benchmark`, `--size`, `--seed`) |
| `flask export-dataset --size 5000` | Only the labelled data set CSV |
| `flask export-master-data` | Snapshot your database so teammates get it on `flask db upgrade` (see below) |
| `flask load-master-data --replace` | Make this database an exact copy of the snapshot (deletes its rows first) |
| `flask simulate-scenario R3` | Run one fraud story (or a combination such as `R1+R4`) and print the decision |
| `python simulate.py --rate 5 --fraud-ratio 0.03 --minutes 2` | Stream payments to the running API |
| `python evaluate.py` | Evaluate 5,000 labelled payments through the running API |
| `python -m pytest` | Run the test suite (uses a temporary `fraude_test` database that it drops when done; never touches `fraude`) |
| `python -m pytest --cov=portal` | …with coverage |
| `python app.py` | API with auto-reload (development) |
| `python wsgi.py` | API with Waitress (what `start_backend.bat` runs) |

### Sharing your data with the team

The data in your `fraude` (customers, merchants, watchlist, rule settings, payments, alerts,
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
| A fraudster attack shows APPROVED (e.g. R1) | That rule's points are below the 40-point hold line in your database (R1 is 35 in the shipped `fraude` data, the seed default is 40). Raise it on the Rules page or run `flask reset-rules`. |
| Every attack is now BLOCKED by R6 | An earlier "Not me" or R9 put the fraudster's device/IP on the watchlist — realistic. Press **Reset demo**, or click "new phone" in the console. |
| Customer app says "This login is locked" | Five wrong passwords lock a customer login; `flask seed-demo --reset` unlocks the demo users. |
| No sound on the customer's alert | Browsers block audio until you click the page; the red alert still appears with a "tap to enable" button. |
| `PermissionError ... app.log -> app.log.1` printed by a `flask` command | Harmless on Windows: the running API holds the log file open, so another process can't rotate it. |
| Start completely fresh | In MySQL Workbench: `DROP DATABASE fraude;` then run `setup.bat` again. |

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
│   ├── portal/services fraud_engine · funds · customer_care · attacker · otp_shield · notifier · simulator · evaluator
│   ├── portal/api/     one blueprint per area (17, incl. customer_api, attacker_api, demo_api)
│   ├── docs/           API.md · RULES.md · ARCHITECTURE.md
│   └── tests/          rules R1–R9, scoring, OTP Shield, auth/RBAC, atomicity, performance, customer app & fraudster demo
├── frontend/           React 18 + Vite + Tailwind + Framer Motion + Recharts
├── docker-compose.yml  mysql + backend + frontend (Nginx) → http://localhost:8080
└── start_all.bat       start everything on Windows
```

Further reading: [API reference](backend/docs/API.md) · [The 9 rules](backend/docs/RULES.md) ·
[Architecture](backend/docs/ARCHITECTURE.md).

API testing in Postman: import `backend/docs/FraudShield.postman_collection.json`, set `password` (and `username`) in the collection variables, and run it top to bottom.

## 10. Tests

```bat
cd backend
venv\Scripts\activate
python -m pytest                 :: 152 tests; uses a temporary fraude_test database it drops afterwards
cd ..\frontend
npm test                         :: device-id / alert de-duplication tests (Node's built-in runner)
npm run build                    :: production build of the web app
```

The backend suite covers the nine rules through the stored procedure, scoring, OTP Shield, staff RBAC,
atomic ingest and idempotency, evaluation, the audit hash chain, and (in
`tests/test_customer_and_fraudster.py`) customer/fraudster authentication and isolation, each attack
R1–R9 and the combined attack through `fraud_engine.ingest`, approved/held/blocked money handling,
"This was me" (paid exactly once) and "Not me" (hold released, fraudster logged out, watchlist, case
status), and the demo reset.

**Known limitations.** The customer app, fraudster console and split screen were verified by the API
tests and a production build, not by automated browser tests (there is no browser-test tooling in
the project), so sound playback and animations are only checked by hand. Alert delivery is polling
(every 2 s), not push. The customer app pays existing payees only (adding payees remains in the OTP
Shield demo bank). The fraudster console is a local simulation and is disabled when `DEMO_MODE` is off.

