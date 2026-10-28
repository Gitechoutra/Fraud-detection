import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BellRing,
  CheckCircle2,
  KeyRound,
  Loader2,
  MapPin,
  MessageSquare,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Smartphone,
  UserPlus,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { bankDemoApi, bankPhone } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import DecisionBadge from '../components/risk/DecisionBadge';
import Button from '../components/ui/Button';
import Tabs from '../components/ui/Tabs';
import usePolling from '../hooks/usePolling';
import { inrRound, shortTime } from '../utils/format';

const MODES = {
  scam: {
    label: 'Scam attempt',
    amount: 48000,
    left: { title: 'Fraudster’s phone', place: 'Delhi · unknown phone', tone: 'blocked' },
    captions: [
      'A scammer got Ravi’s net-banking password through a fake “KYC update” link.',
      'He logs in from his own phone in Delhi — a device Ravi has never used.',
      'He adds a new payee, “Kumar”, to receive the money.',
      'He tries to send ₹48,000. FraudShield checks who is asking BEFORE any OTP is created.',
      'Too many warning signs: no OTP is created at all, so there is nothing to trick Ravi into sharing.',
      'Ravi’s own registered phone asks: “Was this you?”',
      'Ravi answers. If NO: payment blocked, scammer logged out and reported, an alert is raised.',
    ],
  },
  warning: {
    label: 'Genuine · new payee',
    amount: 10000,
    left: { title: 'Ravi’s banking app', place: 'Hyderabad · his own phone', tone: 'approved' },
    captions: [
      'This time it really is Ravi, on his own phone at home.',
      'He logs in as usual.',
      'He adds a new payee, Kiran, for the first time.',
      'He sends ₹10,000 — new payee and bigger than usual, so a few warning points.',
      'Medium risk: the OTP is sent, but the SMS says exactly what it is for and warns him.',
      'He reads it, it’s his own payment, so he types the OTP.',
      'The payment is checked by the 9 rules and goes through.',
    ],
  },
  genuine: {
    label: 'Genuine · usual payee',
    amount: 2000,
    left: { title: 'Ravi’s banking app', place: 'Hyderabad · his own phone', tone: 'approved' },
    captions: [
      'Ravi pays his mother, as he does every month.',
      'He logs in from his own phone.',
      'Amma is an existing payee, so no new payee is needed.',
      'He sends ₹2,000 — normal amount, trusted phone, home city.',
      'Low risk: a normal OTP is sent to his phone.',
      'He types the OTP.',
      'The payment is checked by the 9 rules and goes through in milliseconds.',
    ],
  },
};
const WARNING_PAYEE = { payee_name: 'Kiran (new)', payee_account_no: '60012345678901', payee_ifsc: 'ICIC0004321' };

function Phone({ title, place, tone, children, highlight }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="text-center">
        <p className={clsx('text-sm font-semibold', tone === 'blocked' ? 'text-blocked' : 'text-approved')}>{title}</p>
        <p className="flex items-center justify-center gap-1 text-xs text-muted">
          <MapPin className="h-3 w-3" aria-hidden /> {place}
        </p>
      </div>
      <motion.div
        animate={highlight ? { boxShadow: ['0 0 0 0 rgba(99,102,241,0)', '0 0 0 8px rgba(99,102,241,0.25)', '0 0 0 0 rgba(99,102,241,0)'] } : {}}
        transition={{ duration: 1.6, repeat: highlight ? Infinity : 0 }}
        className="relative w-full max-w-[300px] rounded-[2.6rem] border-[10px] border-[#1c2438] bg-[#1c2438] shadow-soft"
      >
        <div className="absolute left-1/2 top-1.5 z-10 h-4 w-24 -translate-x-1/2 rounded-full bg-[#1c2438]" />
        <div className="flex h-[540px] flex-col overflow-hidden rounded-[2rem] bg-bg">
          <div className="flex items-center justify-between px-5 pb-1 pt-3 text-[10px] text-muted">
            <span>9:41</span>
            <span>5G ▮▮▮</span>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">{children}</div>
        </div>
      </motion.div>
    </div>
  );
}

function BankHeader({ who }) {
  return (
    <div className="mb-3 flex items-center gap-2 border-b border-line pb-3">
      <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-xs font-bold text-white">SB</span>
      <div>
        <p className="text-sm font-semibold leading-tight">Shield Bank</p>
        <p className="text-[11px] leading-tight text-muted">{who || 'Net banking'}</p>
      </div>
    </div>
  );
}

const screen = { initial: { opacity: 0, x: 20 }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -20 }, transition: { duration: 0.2 } };

export default function OtpShieldDemo() {
  const left = useRef(bankPhone());
  const right = useRef(bankPhone());
  const [info, setInfo] = useState(null);
  const [mode, setMode] = useState('scam');
  const [step, setStep] = useState('idle'); // idle | login | payee | amount | waiting | otp | done
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState(null);
  const [payee, setPayee] = useState(null);
  const [shield, setShield] = useState(null);
  const [final, setFinal] = useState(null);
  const [otp, setOtp] = useState('');
  const [rightReady, setRightReady] = useState(false);
  const [approvals, setApprovals] = useState([]);
  const [messages, setMessages] = useState([]);
  const [answer, setAnswer] = useState(null);
  const cfg = MODES[mode];

  useEffect(() => {
    left.current.info().then(setInfo).catch((err) => toast.error(errorMessage(err)));
  }, []);

  const start = useCallback(
    async (m = mode) => {
      if (!info) return;
      setBusy(true);
      setStep('idle');
      setRightReady(false);
      try {
        await bankDemoApi.reset();
        left.current.logout();
        setProfile(null);
        setPayee(null);
        setShield(null);
        setFinal(null);
        setOtp('');
        setApprovals([]);
        setMessages([]);
        setAnswer(null);
        await right.current.login({
          netbanking_id: info.netbanking_id,
          password: info.demo_password,
          device_id: info.trusted_device_id,
          ip_address: info.trusted_ip,
          city: info.home_city,
        });
        setRightReady(true);
        setStep('login');
      } catch (err) {
        toast.error(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [info, mode],
  );

  useEffect(() => {
    // Set the story up once the demo details have loaded (mode changes call start() themselves).
    if (info) start(mode);
  }, [info]); // eslint-disable-line react-hooks/exhaustive-deps

  // Ravi's phone: approvals + messages
  usePolling(
    async () => {
      const [p, n] = await Promise.all([right.current.pending(), right.current.notifications()]);
      setApprovals(p);
      setMessages(n);
    },
    1500,
    rightReady,
  );
  // Requesting phone: wait for Ravi's answer
  usePolling(
    async () => {
      const s = await left.current.status(shield.otp_request_id);
      if (s.final_status !== 'PENDING' && (s.final_status === 'DENIED' || s.final_status === 'EXPIRED' || s.payment)) {
        setFinal(s);
        setStep('done');
      }
    },
    1500,
    step === 'waiting' && !!shield,
  );

  const act = async (fn) => {
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const doLogin = () =>
    act(async () => {
      const scam = mode === 'scam';
      const res = await left.current.login({
        netbanking_id: info.netbanking_id,
        password: info.demo_password,
        device_id: scam ? `SCAM-PHONE-${Math.random().toString(16).slice(2, 8).toUpperCase()}` : info.trusted_device_id,
        device_label: scam ? 'Unknown Android' : info.trusted_device_label,
        ip_address: scam ? `103.${20 + Math.floor(Math.random() * 200)}.${1 + Math.floor(Math.random() * 250)}.${1 + Math.floor(Math.random() * 250)}` : info.trusted_ip,
        city: scam ? 'Delhi' : info.home_city,
      });
      setProfile(res);
      if (mode === 'genuine') {
        setPayee(res.payees[0]);
        setStep('amount');
      } else setStep('payee');
    });

  const doAddPayee = () =>
    act(async () => {
      const p = await left.current.addPayee(mode === 'scam' ? info.scam_payee : WARNING_PAYEE);
      setPayee(p);
      setStep('amount');
    });

  const doSend = () =>
    act(async () => {
      const res = await left.current.send(payee.id, cfg.amount);
      setShield(res);
      setStep(res.decision === 'OTP_BLOCKED_APPROVAL_REQUIRED' ? 'waiting' : 'otp');
    });

  const doVerify = () =>
    act(async () => {
      const res = await left.current.verify(shield.otp_request_id, otp);
      setFinal({ final_status: 'VERIFIED', payment: res.payment });
      setStep('done');
      toast.success(`Payment ${res.payment.status.toLowerCase()}`);
    });

  const respond = (approvalId, a) =>
    act(async () => {
      setAnswer(a);
      await right.current.respond(approvalId, a);
      toast.success(a === 'NO' ? 'Blocked and reported' : 'Approved — device now trusted');
    });

  const latestOtp = useMemo(() => {
    const sms = messages.find((m) => m.kind === 'OTP');
    return sms?.body.match(/OTP (\d{6})/)?.[1] || null;
  }, [messages]);

  const captionIndex = (() => {
    if (step === 'login') return mode === 'scam' ? 0 : 1;
    if (step === 'payee') return 2;
    if (step === 'amount') return 3;
    if (step === 'waiting') return approvals.length ? 5 : 4;
    if (step === 'otp') return messages.some((m) => m.kind === 'OTP') ? 5 : 4;
    if (step === 'done') return 6;
    return 0;
  })();

  const switchMode = (m) => {
    setMode(m);
    start(m);
  };

  return (
    <PageShell
      title="OTP Shield demo"
      subtitle="See how FraudShield stops the classic “share your OTP” scam: when the request looks like a fraudster, no OTP is ever created — Ravi’s own phone is asked instead."
      actions={
        <Button variant="secondary" size="sm" icon={RotateCcw} disabled={busy} onClick={() => start(mode)}>
          Replay story
        </Button>
      }
    >
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Tabs id="otp-mode" value={mode} onChange={switchMode} tabs={Object.entries(MODES).map(([value, m]) => ({ value, label: m.label }))} />
      </div>

      {/* Caption bar */}
      <div className="card mb-6 p-4" aria-live="polite">
        <div className="mb-3 flex gap-1.5" aria-hidden>
          {cfg.captions.map((_, i) => (
            <span key={i} className={clsx('h-1.5 flex-1 rounded-full transition-colors', i <= captionIndex ? 'bg-primary' : 'bg-line')} />
          ))}
        </div>
        <AnimatePresence mode="wait">
          <motion.p key={`${mode}-${captionIndex}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="text-sm sm:text-base">
            <span className="num mr-2 text-muted">Step {captionIndex + 1}/{cfg.captions.length}</span>
            {cfg.captions[captionIndex]}
          </motion.p>
        </AnimatePresence>
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        {/* LEFT: requesting phone */}
        <Phone {...cfg.left} highlight={['login', 'payee', 'amount', 'otp'].includes(step)}>
          <AnimatePresence mode="wait">
            {step === 'idle' && (
              <motion.div key="idle" {...screen} className="flex h-full items-center justify-center pt-40 text-muted">
                <Loader2 className="h-6 w-6 animate-spin" aria-label="Preparing" />
              </motion.div>
            )}

            {step === 'login' && info && (
              <motion.div key="login" {...screen}>
                <BankHeader />
                <p className="mb-3 text-sm font-semibold">Log in</p>
                <label className="label">User ID</label>
                <input className="input mb-3" value={info.netbanking_id} readOnly />
                <label className="label">Password</label>
                <input className="input mb-2" type="password" value={info.demo_password} readOnly />
                {mode === 'scam' && <p className="mb-3 text-[11px] text-blocked">Password stolen through a fake “KYC update” link</p>}
                <Button className="w-full" loading={busy} onClick={doLogin}>
                  Log in
                </Button>
              </motion.div>
            )}

            {step === 'payee' && (
              <motion.div key="payee" {...screen}>
                <BankHeader who={`Hi ${profile?.customer.name.split(' ')[0]}`} />
                <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <UserPlus className="h-4 w-4" /> Add a payee
                </p>
                {Object.entries(mode === 'scam' ? info.scam_payee : WARNING_PAYEE).map(([k, v]) => (
                  <div key={k} className="mb-2">
                    <label className="label">{k.replace('payee_', '').replace('_no', ' number').replace('ifsc', 'IFSC')}</label>
                    <input className="input num" value={v} readOnly />
                  </div>
                ))}
                <Button className="mt-2 w-full" loading={busy} onClick={doAddPayee}>
                  Add payee
                </Button>
              </motion.div>
            )}

            {step === 'amount' && payee && (
              <motion.div key="amount" {...screen}>
                <BankHeader who={`Balance ${inrRound(profile?.account.balance)}`} />
                <p className="mb-3 text-sm font-semibold">Send money</p>
                <div className="mb-3 rounded-xl border border-line bg-surface2 p-3">
                  <p className="text-xs text-muted">To</p>
                  <p className="font-medium">{payee.payee_name}</p>
                  <p className="mono text-xs text-muted">{payee.payee_account_no}</p>
                </div>
                <p className="text-xs text-muted">Amount</p>
                <p className="num mb-4 text-3xl font-semibold">{inrRound(cfg.amount)}</p>
                <Button className="w-full" loading={busy} onClick={doSend}>
                  Send {inrRound(cfg.amount)}
                </Button>
              </motion.div>
            )}

            {step === 'waiting' && (
              <motion.div key="waiting" {...screen} className="flex flex-col items-center pt-10 text-center">
                <motion.span
                  animate={{ scale: [1, 1.08, 1] }}
                  transition={{ repeat: Infinity, duration: 1.6 }}
                  className="mb-4 rounded-3xl bg-primary-soft p-4 text-primary"
                >
                  <Smartphone className="h-10 w-10" />
                </motion.span>
                <p className="font-semibold">{shield?.message}</p>
                <p className="mt-2 text-xs text-muted">No OTP was sent. Only Ravi’s registered phone can approve this.</p>
                <div className="mt-5 w-full rounded-xl border border-line bg-surface2 p-3 text-left">
                  <p className="mb-1 text-xs font-medium text-muted">Why FraudShield is suspicious ({shield?.risk_points} points)</p>
                  <ul className="space-y-1 text-[11px]">
                    {shield?.signals.map((s) => (
                      <li key={s.code} className="flex justify-between gap-2">
                        <span>{s.text}</span>
                        <span className="num text-muted">+{s.points}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <Loader2 className="mt-4 h-5 w-5 animate-spin text-muted" aria-label="Waiting" />
              </motion.div>
            )}

            {step === 'otp' && (
              <motion.div key="otp" {...screen}>
                <BankHeader />
                <p className="mb-1 flex items-center gap-2 text-sm font-semibold">
                  <KeyRound className="h-4 w-4" /> Enter OTP
                </p>
                <p className="mb-3 text-xs text-muted">{shield?.message}</p>
                <input
                  className="input num mb-2 text-center text-2xl tracking-[0.4em]"
                  inputMode="numeric"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                  aria-label="One-time password"
                />
                {latestOtp && otp !== latestOtp && (
                  <button onClick={() => setOtp(latestOtp)} className="mb-3 w-full rounded-lg py-1 text-xs text-primary hover:underline">
                    Copy the OTP from the SMS on the right
                  </button>
                )}
                <Button className="w-full" loading={busy} disabled={otp.length !== 6} onClick={doVerify}>
                  Confirm payment
                </Button>
                <p className="mt-3 text-[11px] text-muted">Risk check: {shield?.risk_points} points</p>
              </motion.div>
            )}

            {step === 'done' && final && (
              <motion.div key="done" {...screen} className="flex flex-col items-center pt-8 text-center">
                {final.final_status === 'DENIED' ? (
                  <>
                    <motion.span initial={{ scale: 0.6 }} animate={{ scale: 1 }} className="mb-4 rounded-3xl bg-blocked-soft p-4 text-blocked">
                      <ShieldX className="h-12 w-12" />
                    </motion.span>
                    <p className="text-lg font-semibold">Payment blocked</p>
                    <p className="mt-2 text-sm text-muted">The account owner said this wasn’t them. This device has been logged out.</p>
                  </>
                ) : final.final_status === 'EXPIRED' ? (
                  <p className="text-lg font-semibold">Request expired — no money moved.</p>
                ) : (
                  <>
                    <motion.span initial={{ scale: 0.6 }} animate={{ scale: 1 }} className="mb-4 rounded-3xl bg-approved-soft p-4 text-approved">
                      <CheckCircle2 className="h-12 w-12" />
                    </motion.span>
                    <DecisionBadge status={final.payment.status} size="lg" />
                    <p className="num mt-3 text-2xl font-semibold">{inrRound(final.payment.amount)}</p>
                    <p className="mt-1 text-xs text-muted">Decided in {final.payment.decision_ms?.toFixed(1)} ms · risk {final.payment.risk_score}/100</p>
                    <Link to={`/app/transactions/${final.payment.txn_id}`} className="mt-3 text-sm text-primary hover:underline">
                      See why
                    </Link>
                  </>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </Phone>

        {/* RIGHT: Ravi's trusted phone */}
        <Phone title="Ravi’s phone" place="Hyderabad · registered phone" tone="approved" highlight={approvals.length > 0 && !answer}>
          <BankHeader who="Notifications" />
          <AnimatePresence>
            {approvals.map((a) => (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, y: -30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ type: 'spring', stiffness: 260, damping: 22 }}
                className="mb-3 rounded-2xl border border-review/40 bg-review-soft p-4"
              >
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <BellRing className="h-4 w-4 text-review" /> Was this you?
                </p>
                <p className="mt-2 text-sm">{messages.find((m) => m.kind === 'APPROVAL' && m.ref_id === a.id)?.body}</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button variant="success" size="sm" loading={busy && answer === 'YES'} disabled={busy} onClick={() => respond(a.id, 'YES')}>
                    YES, it’s me
                  </Button>
                  <Button variant="danger" size="sm" loading={busy && answer === 'NO'} disabled={busy} onClick={() => respond(a.id, 'NO')}>
                    NO, block it
                  </Button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.li
                  key={m.id}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={clsx(
                    'rounded-2xl border p-3 text-sm',
                    m.kind === 'OTP' && m.body.includes('DO NOT') ? 'border-review/40 bg-review-soft' : 'border-line bg-surface',
                  )}
                >
                  <p className="mb-1 flex items-center justify-between text-[11px] text-muted">
                    <span className="flex items-center gap-1">
                      {m.channel === 'SMS' ? <MessageSquare className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                      {m.channel === 'SMS' ? 'SMS · Shield Bank' : 'Shield Bank app'} · {m.title}
                    </span>
                    {shortTime(m.created_at)}
                  </p>
                  {m.body}
                </motion.li>
              ))}
            </AnimatePresence>
            {messages.length === 0 && (
              <li className="pt-20 text-center text-xs text-muted">
                <ShieldAlert className="mx-auto mb-2 h-6 w-6" />
                No messages yet. Bank alerts and OTPs will appear here.
              </li>
            )}
          </ul>
        </Phone>
      </div>

      {step === 'done' && final?.final_status === 'DENIED' && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card mt-6 p-5">
          <p className="font-semibold">What FraudShield did when Ravi said NO</p>
          <ul className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
            <li>• The scammer’s phone was logged out of Ravi’s account.</li>
            <li>• Payee “Kumar” is frozen for 24 hours.</li>
            <li>• The phone, internet address and Kumar’s account were added to the watchlist.</li>
            <li>
              • A high-priority alert was raised —{' '}
              <Link to="/app/alerts" className="text-primary hover:underline">
                see the alert queue
              </Link>
              .
            </li>
          </ul>
        </motion.div>
      )}
    </PageShell>
  );
}
