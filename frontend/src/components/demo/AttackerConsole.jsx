import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, KeyRound, Loader2, LogOut, MapPin, RotateCcw, Skull, Smartphone, Zap } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { errorMessage } from '../../api/client';
import { attackerApi } from '../../api/demoClients';
import usePolling from '../../hooks/usePolling';
import { CITIES, getCity, getDeviceId, resetDeviceId, setCity } from '../../utils/device';
import { inr, shortTime } from '../../utils/format';
import { ALERT_POLL_MS } from '../../utils/polling';

const HOW = { PHISHING_LINK: 'Phishing link', OTP_CALL: 'OTP call', CARD_SKIMMING: 'Card skimming', SIM_SWAP: 'SIM swap' };
const DECISION_CLS = {
  APPROVED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  REVIEW: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  BLOCKED: 'bg-red-500/15 text-red-300 border-red-500/40',
  REFUSED: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
};
const RESPONSE = { PENDING: 'Victim: waiting', CONFIRMED_ME: 'Victim: "This was me"', REPORTED_NOT_ME: 'Victim: "Not me" — reported' };
const FUNDS = { DEBITED: 'money taken', HELD: 'money on hold', PAID_AFTER_REVIEW: 'paid after victim confirmed', RELEASED: 'hold released', NOT_MOVED: 'no money moved' };

function Decision({ status }) {
  return <span className={clsx('rounded-full border px-2 py-0.5 text-[11px] font-semibold', DECISION_CLS[status] || DECISION_CLS.REFUSED)}>{status}</span>;
}

function Banner() {
  return (
    <div className="flex items-center justify-center gap-2 bg-red-600 px-3 py-1.5 text-center text-xs font-bold uppercase tracking-widest text-white" role="note">
      <AlertTriangle className="h-4 w-4" aria-hidden /> Simulation only — local demo with synthetic data
    </div>
  );
}

function Login({ onDone, notice }) {
  const [username, setUsername] = useState('hacker1');
  const [password, setPassword] = useState('Hacker@123');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      onDone(await attackerApi.login(username.trim().toLowerCase(), password));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-3 p-6">
      <Skull className="mx-auto h-10 w-10 text-red-400" aria-hidden />
      <p className="text-center text-lg font-semibold">Fraudster console</p>
      {notice && <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">{notice}</p>}
      <div className="flex justify-center gap-2 text-xs">
        {['hacker1', 'hacker2'].map((u) => (
          <button key={u} type="button" onClick={() => setUsername(u)} className={clsx('rounded-full border px-3 py-1', u === username ? 'border-red-400 text-red-300' : 'border-slate-600 text-slate-400')}>
            {u}
          </button>
        ))}
      </div>
      <input className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm" aria-label="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
      <input className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm" aria-label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="text-xs text-red-300">{error}</p>}
      <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-60">
        {busy && <Loader2 className="h-4 w-4 animate-spin" />} Log in
      </button>
      <p className="text-center text-[11px] text-slate-500">Demo: hacker1 / hacker2 · Hacker@123</p>
    </form>
  );
}

function Result({ r }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-slate-700 bg-slate-900/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          {r.scenario} · {r.title} <span className="text-xs font-normal text-slate-400">→ {r.victim.name} (from {r.from.city})</span>
        </p>
        <span className="flex items-center gap-2 text-xs">
          Bank decision <Decision status={r.bank_decision} />
        </span>
      </div>
      <ol className="mt-2 space-y-1.5 text-xs">
        {r.steps.map((s, i) => (
          <li key={i} className={clsx('rounded-lg px-2 py-1.5', s.attack === false ? 'bg-slate-800/40 text-slate-400' : 'bg-slate-800/80')}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{s.label}</span>
              {s.status && <Decision status={s.status} />}
              {s.error && <span className="text-red-300">Refused: {s.error}</span>}
            </div>
            {s.status && (
              <p className="mt-1 font-mono text-[10px] text-slate-400">
                {s.external_ref} · risk {s.risk_score}/100 · {FUNDS[s.funds_status] || ''}
                {s.rules.length ? ` · rules ${s.rules.map((h) => h.rule_code).join(', ')}` : ' · no rule fired'}
              </p>
            )}
            {s.rules?.map((h) => (
              <p key={h.rule_code} className="text-[11px] text-amber-200/90">
                {h.rule_code}: {h.detail_text}
              </p>
            ))}
          </li>
        ))}
      </ol>
      <p className={clsx('mt-2 text-xs', r.expected_rules_fired ? 'text-emerald-300' : 'text-amber-300')}>
        Expected {r.expected_rules.join(' + ')} · fired {r.rules_fired.join(', ') || 'none'}
      </p>
    </motion.div>
  );
}

/** The fraudster's screen. Every button calls the real API; the decision
 *  shown is the one the bank's SQL engine made. */
export default function AttackerConsole({ compact = false, onActivity }) {
  const [me, setMe] = useState(null);
  const [running, setRunning] = useState(null);
  const [results, setResults] = useState([]);
  const [events, setEvents] = useState([]);
  const [notice, setNotice] = useState('');
  const [device, setDevice] = useState(() => getDeviceId('attacker'));

  const logoutLocal = useCallback((message) => {
    setMe(null);
    setEvents([]);
    if (message) setNotice(message);
  }, []);
  useEffect(() => {
    if (attackerApi.hasSession()) attackerApi.me().then(setMe).catch(() => logoutLocal());
    const onLogout = (e) =>
      logoutLocal(e.detail?.code === 'SESSION_REVOKED' ? 'The bank ended your session: the victim reported you ("Not me").' : e.detail?.message);
    window.addEventListener('fs:attacker-logout', onLogout);
    return () => window.removeEventListener('fs:attacker-logout', onLogout);
  }, [logoutLocal]);

  usePolling(async () => setEvents(await attackerApi.events()), ALERT_POLL_MS, Boolean(me));

  const run = async (code) => {
    setRunning(code);
    try {
      const r = await attackerApi.run(code);
      setResults((prev) => [r, ...prev].slice(0, 6));
      onActivity?.(r);
    } catch (err) {
      setNotice(errorMessage(err));
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className={clsx('flex min-h-full flex-col rounded-2xl border border-slate-800 bg-[#0b0f17] text-slate-100', compact ? 'text-sm' : '')}>
      <Banner />
      {!me ? (
        <Login onDone={(m) => { setNotice(''); setMe(m); }} notice={notice} />
      ) : (
        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="flex items-center gap-2 font-semibold">
                <Skull className="h-5 w-5 text-red-400" aria-hidden /> {me.display_name} <span className="text-xs font-normal text-slate-400">@{me.username}</span>
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                <span className="flex items-center gap-1">
                  <Smartphone className="h-3 w-3" /> {device}
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  <select
                    aria-label="Fraudster city"
                    className="rounded border border-slate-700 bg-slate-900 px-1 py-0.5"
                    value={getCity('attacker', me.base_city)}
                    onChange={(e) => {
                      setCity('attacker', e.target.value);
                      attackerApi.me().then(setMe);
                    }}
                  >
                    {CITIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </span>
                <button type="button" className="underline" onClick={() => setDevice(resetDeviceId('attacker'))}>
                  new phone
                </button>
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => attackerApi.resetDemo().then((r) => { setResults([]); setNotice(`Demo reset: ${r.reset.join(', ')}`); }).catch((e) => setNotice(errorMessage(e)))}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Reset demo
              </button>
              <button type="button" onClick={() => attackerApi.logout().finally(() => logoutLocal())} className="flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs">
                <LogOut className="h-3.5 w-3.5" /> Log out
              </button>
            </div>
          </div>
          {notice && (
            <button type="button" onClick={() => setNotice('')} className="w-full rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-left text-xs text-amber-200">
              {notice}
            </button>
          )}

          <section>
            <p className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              <KeyRound className="h-3.5 w-3.5" /> Stolen credentials
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {me.credentials.map((c) => (
                <div key={c.id} className="rounded-xl border border-slate-800 bg-slate-900/60 p-2.5 text-xs">
                  <p className="font-semibold">
                    {c.victim} <span className="font-normal text-slate-400">@{c.username}</span>
                  </p>
                  <p className="text-slate-400">
                    {c.home_city} · {c.account} · card {c.card} {c.account_status === 'DORMANT' && '· dormant'}
                  </p>
                  <p className="text-slate-400">
                    password {c.password} · via <span className="text-red-300">{HOW[c.obtained_via]}</span>
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Attacks (each goes through the real bank API)</p>
            <div className={clsx('grid gap-2', compact ? 'grid-cols-2' : 'grid-cols-2 lg:grid-cols-3')}>
              {me.scenarios.filter((s) => s.code !== 'COMBINED').map((s) => (
                <button
                  key={s.code}
                  type="button"
                  disabled={Boolean(running)}
                  onClick={() => run(s.code)}
                  title={s.story}
                  className="rounded-xl border border-slate-700 bg-slate-900 p-2.5 text-left text-xs transition hover:border-red-500/60 disabled:opacity-50"
                >
                  <span className="flex items-center gap-1 font-semibold">
                    {running === s.code ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className="text-red-400">{s.code}</span>} {s.title}
                  </span>
                  {!compact && <span className="mt-0.5 block text-[11px] text-slate-400">{s.story}</span>}
                </button>
              ))}
            </div>
            <button
              type="button"
              disabled={Boolean(running)}
              onClick={() => run('COMBINED')}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 py-2.5 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-60"
            >
              {running === 'COMBINED' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />} Run combined attack
            </button>
          </section>

          <AnimatePresence>
            {results.map((r, i) => (
              <Result key={`${r.scenario}-${results.length - i}`} r={r} />
            ))}
          </AnimatePresence>

          {events.length > 0 && (
            <section>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">My attack payments (live)</p>
              <ul className="space-y-1 text-xs">
                {events.slice(0, compact ? 6 : 12).map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-900/60 px-2 py-1.5">
                    <span className="min-w-0">
                      <span className="text-slate-400">{shortTime(e.created_at)}</span> {e.scenario} · {e.victim} · {inr(e.amount)}
                      <span className="text-slate-500"> · {FUNDS[e.funds_status] || ''}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      {e.customer_response && <span className={clsx('text-[11px]', e.customer_response === 'REPORTED_NOT_ME' ? 'text-red-300' : 'text-slate-400')}>{RESPONSE[e.customer_response]}</span>}
                      <Decision status={e.status} />
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
