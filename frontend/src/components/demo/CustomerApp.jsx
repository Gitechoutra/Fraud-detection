import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Bell,
  CheckCircle2,
  History,
  Home,
  Loader2,
  LogOut,
  Send,
  ShieldAlert,
  Smartphone,
  User,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../api/client';
import { customerApi } from '../../api/demoClients';
import usePolling from '../../hooks/usePolling';
import { CITIES, getCity, getDeviceId, newAlerts, setCity } from '../../utils/device';
import { inr, shortDate, timeAgo } from '../../utils/format';
import { ALERT_POLL_MS } from '../../utils/polling';
import DecisionBadge from '../risk/DecisionBadge';
import Button from '../ui/Button';
import { playAlarm, unlockAudio } from './alarm';

const DEMO_USERS = ['ravi', 'priya', 'suresh', 'lakshmi', 'arjun'];
const TABS = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'pay', label: 'Pay', icon: Send },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'history', label: 'History', icon: History },
  { id: 'profile', label: 'Profile', icon: User },
];
const FUNDS = {
  DEBITED: 'Paid',
  HELD: 'Money on hold',
  PAID_AFTER_REVIEW: 'Paid after you confirmed',
  RELEASED: 'Hold released — not paid',
  NOT_MOVED: 'No money moved',
};
const RESPONSE = { PENDING: 'Waiting for you', CONFIRMED_ME: 'You said: this was me', REPORTED_NOT_ME: 'You said: not me' };

function newKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function Login({ onDone }) {
  const [username, setUsername] = useState('ravi');
  const [password, setPassword] = useState('Ravi@123');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    unlockAudio(); // a click: the browser now allows the alert sound
    try {
      onDone(await customerApi.login(username.trim().toLowerCase(), password));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="flex h-full flex-col justify-center gap-3 p-2">
      <div className="mb-2 text-center">
        <span className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-sm font-bold text-white">SB</span>
        <p className="font-semibold">Shield Bank</p>
        <p className="text-xs text-muted">Log in to your account</p>
      </div>
      <div className="flex flex-wrap justify-center gap-1">
        {DEMO_USERS.map((u) => (
          <button
            key={u}
            type="button"
            onClick={() => {
              setUsername(u);
              setPassword(`${u[0].toUpperCase()}${u.slice(1)}@123`);
            }}
            className={clsx('rounded-full border px-2 py-0.5 text-[11px]', u === username ? 'border-primary bg-primary-soft text-primary' : 'border-line text-muted')}
          >
            {u}
          </button>
        ))}
      </div>
      <input className="input" aria-label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
      <input className="input" aria-label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
      {error && <p className="rounded-lg bg-blocked-soft px-3 py-2 text-xs text-blocked">{error}</p>}
      <Button type="submit" loading={busy}>
        Log in
      </Button>
      <p className="text-center text-[11px] text-muted">Demo password: Name@123 (e.g. Ravi@123)</p>
    </form>
  );
}

function FraudAlarm({ alert, soundOk, onSound, onAnswer, onClose }) {
  if (!alert) return null;
  const danger = alert.severity === 'DANGER';
  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="absolute inset-x-2 top-10 z-30"
      role="alertdialog"
      aria-label="Fraud alert"
    >
      <motion.div
        animate={{ boxShadow: ['0 0 0 0 rgba(239,68,68,0.6)', '0 0 0 14px rgba(239,68,68,0)'] }}
        transition={{ duration: 1.1, repeat: Infinity }}
        className="rounded-2xl border-2 border-blocked bg-blocked p-3 text-white"
      >
        <div className="flex items-start gap-2">
          <motion.span animate={{ rotate: [0, -12, 12, -12, 0] }} transition={{ duration: 0.6, repeat: Infinity, repeatDelay: 0.6 }}>
            <ShieldAlert className="h-6 w-6" aria-hidden />
          </motion.span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold leading-tight">{danger ? 'Fraud stopped on your account' : 'Was this you?'}</p>
            <p className="mt-0.5 text-xs font-semibold">{alert.title}</p>
            <p className="mt-1 text-xs opacity-95">{alert.body}</p>
            <p className="mt-1 font-mono text-[10px] opacity-80">
              Ref {alert.external_ref} · {timeAgo(alert.created_at)}
            </p>
          </div>
        </div>
        {!soundOk && (
          <button type="button" onClick={onSound} className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-white/15 py-1 text-[11px]">
            <VolumeX className="h-3.5 w-3.5" /> Sound is blocked by the browser — tap to enable
          </button>
        )}
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => onAnswer('confirm', alert)} className="rounded-xl bg-white/15 py-2 text-xs font-semibold hover:bg-white/25">
            This was me
          </button>
          <button type="button" onClick={() => onAnswer('report', alert)} className="rounded-xl bg-white py-2 text-xs font-bold text-blocked">
            Not me
          </button>
        </div>
        <button type="button" onClick={onClose} className="mt-2 w-full text-center text-[10px] underline opacity-80">
          Decide later (in Alerts)
        </button>
      </motion.div>
    </motion.div>
  );
}

function AlertCard({ a, onAnswer }) {
  const tone = a.severity === 'DANGER' ? 'border-blocked/40 bg-blocked-soft' : a.severity === 'WARNING' ? 'border-review/40 bg-review-soft' : 'border-line bg-surface2';
  return (
    <div className={clsx('rounded-xl border p-3 text-xs', tone)}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold">{a.title}</p>
        <span className="shrink-0 text-[10px] text-muted">{timeAgo(a.created_at)}</span>
      </div>
      <p className="mt-1">{a.body}</p>
      <p className="mt-1 font-mono text-[10px] text-muted">
        {a.external_ref} · {a.severity} · {FUNDS[a.funds_status] || a.txn_status}
      </p>
      {a.action_status === 'PENDING' && a.severity !== 'INFO' ? (
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => onAnswer('confirm', a)} className="rounded-lg border border-line bg-surface py-1.5 font-medium">
            This was me
          </button>
          <button type="button" onClick={() => onAnswer('report', a)} className="rounded-lg bg-blocked py-1.5 font-semibold text-white">
            Not me
          </button>
        </div>
      ) : (
        <p className="mt-2 font-medium">{RESPONSE[a.action_status]}</p>
      )}
    </div>
  );
}

function PayForm({ payees, available, onPaid }) {
  const [payee, setPayee] = useState('');
  const [amount, setAmount] = useState('');
  const [channel, setChannel] = useState('UPI');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const key = useRef(newKey()); // same key if the same attempt is retried
  useEffect(() => {
    key.current = newKey();
  }, [payee, amount, channel]);
  useEffect(() => {
    if (!payee && payees.length) setPayee(String(payees[0].id));
  }, [payees, payee]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const res = await customerApi.pay({ beneficiary_id: Number(payee), amount: Number(amount), channel, idempotency_key: key.current });
      setResult(res);
      key.current = newKey();
      onPaid();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm font-semibold">Send money</p>
      <label className="block text-xs">
        To
        <select className="input mt-1" value={payee} onChange={(e) => setPayee(e.target.value)}>
          {payees.map((p) => (
            <option key={p.id} value={p.id} disabled={Boolean(p.on_hold_until)}>
              {p.payee_name} ({p.masked_account}){p.on_hold_until ? ' — on hold' : ''}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-xs">
        Amount (₹)
        <input className="input mt-1" type="number" min="1" max="200000" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} />
      </label>
      <div className="flex gap-2 text-xs">
        {['UPI', 'NETBANKING'].map((c) => (
          <button key={c} type="button" onClick={() => setChannel(c)} className={clsx('flex-1 rounded-lg border py-1.5', c === channel ? 'border-primary bg-primary-soft text-primary' : 'border-line')}>
            {c === 'UPI' ? 'UPI' : 'Net banking'}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-muted">Available {inr(available)} · limit ₹2,00,000 per payment</p>
      {error && <p className="rounded-lg bg-blocked-soft px-3 py-2 text-xs text-blocked">{error}</p>}
      <Button type="submit" loading={busy} className="w-full" icon={Send}>
        Pay
      </Button>
      {result && (
        <div className="rounded-xl border border-line bg-surface2 p-3 text-xs">
          <div className="flex items-center justify-between">
            <DecisionBadge status={result.status} />
            <span className="font-mono text-[10px] text-muted">{result.external_ref}</span>
          </div>
          <p className="mt-2">{FUNDS[result.funds_status] || ''}</p>
          {result.rules.map((r) => (
            <p key={r.rule_code} className="mt-1 text-muted">
              {r.rule_code}: {r.detail_text}
            </p>
          ))}
        </div>
      )}
    </form>
  );
}

/**
 * The customer's phone. `compact` is used by the split-screen demo.
 * Everything shown comes from the backend; nothing is decided here.
 */
export default function CustomerApp({ compact = false }) {
  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState('home');
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const [alarm, setAlarm] = useState(null);
  const [soundOk, setSoundOk] = useState(true);
  const [payees, setPayees] = useState([]);
  const [history, setHistory] = useState(null);
  const [answer, setAnswer] = useState(null); // { kind, alert }
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const seen = useRef(null); // alert ids already known (no repeat sound / popup)
  const loggedIn = Boolean(profile);

  const logoutLocal = useCallback((message) => {
    setProfile(null);
    setAlerts([]);
    seen.current = null;
    setAlarm(null);
    if (message) setNotice(message);
  }, []);

  useEffect(() => {
    if (customerApi.hasSession()) customerApi.me().then(setProfile).catch(() => logoutLocal());
    const onLogout = (e) => logoutLocal(e.detail?.message || 'Please log in again.');
    window.addEventListener('fs:customer-logout', onLogout);
    return () => window.removeEventListener('fs:customer-logout', onLogout);
  }, [logoutLocal]);

  useEffect(() => {
    if (profile) customerApi.setHomeCity(profile.customer.home_city);
  }, [profile]);

  const poll = useCallback(async () => {
    const [me, res] = await Promise.all([customerApi.me(), customerApi.alerts()]);
    setProfile(me);
    setAlerts(res.items);
    setUnread(res.unread);
    if (seen.current === null) {
      seen.current = new Set(res.items.map((a) => a.id)); // what was there at login
      const waiting = res.items.find((a) => a.action_status === 'PENDING' && a.severity !== 'INFO');
      if (waiting) setAlarm(waiting);
      return;
    }
    const fresh = newAlerts(res.items, seen.current);
    fresh.forEach((a) => seen.current.add(a.id));
    const urgent = fresh.filter((a) => a.severity !== 'INFO' && a.action_status === 'PENDING').pop();
    if (urgent) {
      setAlarm(urgent);
      setSoundOk(await playAlarm());
    }
  }, []);
  usePolling(poll, ALERT_POLL_MS, loggedIn);

  useEffect(() => {
    if (!loggedIn) return;
    if (tab === 'pay') customerApi.payees().then(setPayees).catch(() => {});
    if (tab === 'history') customerApi.history().then(setHistory).catch(() => {});
    if (tab === 'alerts' && unread) customerApi.markRead().then(() => setUnread(0)).catch(() => {});
  }, [tab, loggedIn, unread, alerts.length]);

  const startAnswer = (kind, alert) => {
    setAlarm(null);
    setPassword('');
    setAnswer({ kind, alert });
  };

  const submitAnswer = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      const res = answer.kind === 'confirm' ? await customerApi.confirm(answer.alert.id, password) : await customerApi.report(answer.alert.id);
      setNotice(res.message);
      setAnswer(null);
      poll();
    } catch (err) {
      setNotice(errorMessage(err));
      if (err.response?.status !== 401) setAnswer(answer.kind === 'confirm' ? answer : null);
    } finally {
      setBusy(false);
    }
  };

  const frame = compact ? 'h-[560px] max-w-[320px]' : 'h-[640px] max-w-[360px]';
  return (
    <div className={clsx('relative mx-auto w-full rounded-[2.4rem] border-[10px] border-[#1c2438] bg-[#1c2438] shadow-soft', frame)}>
      <div className="absolute left-1/2 top-1 z-40 h-4 w-24 -translate-x-1/2 rounded-full bg-[#1c2438]" />
      <div className="relative flex h-full flex-col overflow-hidden rounded-[1.8rem] bg-bg">
        <div className="flex items-center justify-between px-5 pb-1 pt-3 text-[10px] text-muted">
          <span>Shield Bank</span>
          {loggedIn && (
            <button type="button" onClick={() => setTab('alerts')} className="relative" aria-label={`Alerts, ${unread} unread`}>
              <motion.span animate={unread ? { rotate: [0, -15, 15, 0] } : {}} transition={{ duration: 0.5, repeat: unread ? Infinity : 0, repeatDelay: 1.5 }} className="inline-block">
                <Bell className={clsx('h-4 w-4', unread ? 'text-blocked' : 'text-muted')} />
              </motion.span>
              {unread > 0 && <span className="absolute -right-2 -top-1.5 rounded-full bg-blocked px-1 text-[9px] font-bold text-white">{unread}</span>}
            </button>
          )}
        </div>

        <AnimatePresence>
          {alarm && (
            <FraudAlarm
              alert={alarm}
              soundOk={soundOk}
              onSound={async () => setSoundOk(await playAlarm())}
              onAnswer={startAnswer}
              onClose={() => setAlarm(null)}
            />
          )}
        </AnimatePresence>

        <div className="flex-1 overflow-y-auto px-4 pb-3">
          {notice && (
            <button type="button" onClick={() => setNotice('')} className="mb-2 w-full rounded-lg bg-primary-soft px-3 py-2 text-left text-xs text-primary">
              {notice}
            </button>
          )}
          {!loggedIn ? (
            <Login onDone={(p) => { setNotice(''); setProfile(p); setTab('home'); }} />
          ) : answer ? (
            <form onSubmit={submitAnswer} className="space-y-3 pt-4">
              <p className="text-sm font-semibold">{answer.kind === 'confirm' ? 'Confirm it was you' : 'Report: this was not me'}</p>
              <p className="text-xs text-muted">{answer.alert.title}</p>
              {answer.kind === 'confirm' ? (
                <>
                  <p className="text-xs">Enter your password again. This phone will be trusted and a held payment will be completed once.</p>
                  <input className="input" type="password" aria-label="Password" required value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
                </>
              ) : (
                <p className="text-xs">We will release any held money without paying it, log the other person out, and block the device and payee they used.</p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Button variant="secondary" onClick={() => setAnswer(null)}>
                  Cancel
                </Button>
                <Button type="submit" variant={answer.kind === 'confirm' ? 'success' : 'danger'} loading={busy}>
                  {answer.kind === 'confirm' ? 'Confirm' : 'Report'}
                </Button>
              </div>
            </form>
          ) : tab === 'home' ? (
            <div className="space-y-3 pt-2">
              <p className="text-sm">Hello, {profile.customer.name.split(' ')[0]}</p>
              <div className="rounded-2xl bg-primary p-4 text-white">
                <p className="text-[11px] opacity-80">Available balance · {profile.account.masked_no}</p>
                <p className="text-2xl font-semibold">{inr(profile.account.available)}</p>
                <div className="mt-2 flex justify-between text-[11px] opacity-90">
                  <span>Balance {inr(profile.account.balance)}</span>
                  <span>On hold {inr(profile.account.held_amount)}</span>
                </div>
              </div>
              {profile.account.status === 'DORMANT' && <p className="rounded-lg bg-review-soft px-3 py-2 text-xs text-review">This account has been inactive for a long time.</p>}
              <p className="text-xs font-semibold">Latest alerts</p>
              {alerts.slice(0, 3).map((a) => (
                <AlertCard key={a.id} a={a} onAnswer={startAnswer} />
              ))}
              {!alerts.length && <p className="text-xs text-muted">No alerts. Your account looks normal.</p>}
            </div>
          ) : tab === 'pay' ? (
            <PayForm payees={payees} available={profile.account.available} onPaid={poll} />
          ) : tab === 'alerts' ? (
            <div className="space-y-2 pt-2">
              <p className="text-sm font-semibold">Alerts</p>
              {alerts.map((a) => (
                <AlertCard key={a.id} a={a} onAnswer={startAnswer} />
              ))}
              {!alerts.length && <p className="text-xs text-muted">No alerts yet.</p>}
            </div>
          ) : tab === 'history' ? (
            <div className="space-y-1.5 pt-2">
              <p className="text-sm font-semibold">History</p>
              {!history && <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted" />}
              {history?.items.map((t) => (
                <div key={t.id} className="flex items-center justify-between gap-2 border-b border-line py-1.5 text-xs">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{t.counterparty || t.channel}</p>
                    <p className="text-[10px] text-muted">
                      {shortDate(t.txn_time)} · {t.city}
                      {t.funds_status ? ` · ${FUNDS[t.funds_status]}` : ''}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-mono">−{inr(t.amount)}</p>
                    <DecisionBadge status={t.status} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3 pt-2 text-xs">
              <p className="text-sm font-semibold">{profile.customer.name}</p>
              <p className="text-muted">
                @{profile.username} · {profile.customer.home_city} · {profile.customer.phone}
              </p>
              <p>Account {profile.account.masked_no} · Card •••• {profile.card.last4}</p>
              <div className="rounded-xl border border-line p-3">
                <p className="flex items-center gap-1 font-medium">
                  <Smartphone className="h-3.5 w-3.5" /> This device
                </p>
                <p className="mt-1 break-all font-mono text-[10px]">{getDeviceId('customer')}</p>
                <p className="mt-1 flex items-center gap-1">
                  {profile.device.is_trusted ? <CheckCircle2 className="h-3.5 w-3.5 text-approved" /> : <ShieldAlert className="h-3.5 w-3.5 text-review" />}
                  {profile.device.is_trusted ? 'Trusted device' : 'Not trusted yet (a private window is a new device)'}
                </p>
                <label className="mt-2 block">
                  Demo location
                  <select
                    className="input mt-1"
                    value={getCity('customer', profile.customer.home_city)}
                    onChange={(e) => {
                      setCity('customer', e.target.value);
                      poll();
                    }}
                  >
                    {CITIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              </div>
              <button type="button" onClick={() => { unlockAudio(); setSoundOk(true); }} className="flex items-center gap-1 text-muted">
                <Volume2 className="h-3.5 w-3.5" /> Enable alert sound
              </button>
              <Button variant="secondary" icon={LogOut} className="w-full" onClick={() => customerApi.logout().finally(() => logoutLocal())}>
                Log out
              </Button>
            </div>
          )}
        </div>

        {loggedIn && !answer && (
          <nav className="grid grid-cols-5 border-t border-line bg-surface text-[10px]">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button key={t.id} type="button" onClick={() => setTab(t.id)} className={clsx('relative flex flex-col items-center gap-0.5 py-2', tab === t.id ? 'text-primary' : 'text-muted')}>
                  <Icon className="h-4 w-4" aria-hidden />
                  {t.label}
                  {t.id === 'alerts' && unread > 0 && <span className="absolute right-3 top-1 h-2 w-2 rounded-full bg-blocked" />}
                </button>
              );
            })}
          </nav>
        )}
      </div>
    </div>
  );
}
