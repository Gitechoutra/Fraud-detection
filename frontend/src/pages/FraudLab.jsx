import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, ExternalLink, Layers, Loader2, Play, Square, XCircle } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { simulatorApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import DecisionBadge from '../components/risk/DecisionBadge';
import RiskGauge from '../components/risk/RiskGauge';
import RuleChip from '../components/risk/RuleChip';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import usePolling from '../hooks/usePolling';
import { inr, num } from '../utils/format';
import { NORMAL_SCENARIO, RULE_CODES, RULES } from '../utils/ruleInfo';

const SCENARIOS = [
  { code: 'NORMAL', ...NORMAL_SCENARIO, story: NORMAL_SCENARIO.what },
  ...RULE_CODES.map((code) => ({ code, icon: RULES[code].icon, name: RULES[code].name, story: RULES[code].example })),
  // Fraud that trips several rules at once (backend simulator.COMBOS).
  ...[
    ['R1+R4', 'A thief on a brand-new phone makes one purchase many times bigger than the owner ever spends.'],
    ['R3+R6', 'Minutes after the owner pays at home, the card is used in another city from a known fraud IP address.'],
    ['R5+R8', 'An account asleep for over 6 months suddenly sends a large amount at 2 o’clock at night.'],
  ].map(([code, story]) => ({ code, icon: Layers, name: code.split('+').map((c) => RULES[c].name).join(' + '), story })),
];

function ResultCard({ result }) {
  const t = result.target;
  const ok = result.expected_rule_fired;
  return (
    <motion.div
      key={t.txn_id}
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="card overflow-hidden"
    >
      <div className={clsx('flex items-center gap-2 px-5 py-3 text-sm font-medium', ok ? 'bg-approved-soft text-approved' : 'bg-blocked-soft text-blocked')}>
        {ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        {result.expected_rule
          ? ok
            ? `${result.expected_rules.length > 1 ? 'Rules' : 'Rule'} ${result.expected_rules.join(' + ')} caught it`
            : `${result.expected_rules.length > 1 ? 'Not all of' : 'Rule'} ${result.expected_rules.join(' + ')} ${result.expected_rules.length > 1 ? 'fired' : 'did not fire'}`
          : ok
            ? 'Normal payment approved, as expected'
            : 'Normal payment was flagged'}
      </div>
      <div className="grid gap-5 p-5 md:grid-cols-[auto_1fr]">
        <div className="flex flex-col items-center gap-2">
          <RiskGauge score={t.risk_score} />
          <DecisionBadge status={t.status} size="lg" />
        </div>
        <div className="min-w-0 space-y-3">
          <p className="text-sm text-muted">{result.story}</p>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <span className="num text-2xl font-semibold">{inr(t.amount)}</span>
            <span className="text-sm text-muted">
              decided in <span className="num text-ink">{t.decision_ms?.toFixed(1)} ms</span>
            </span>
          </div>
          {t.rules.length ? (
            <ul className="space-y-1.5">
              {t.rules.map((h) => (
                <li key={h.rule_code} className="flex items-start gap-2 text-sm">
                  <RuleChip code={h.rule_code} />
                  <span>{h.detail_text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm">No warning signs — all nine checks passed.</p>
          )}
          {t.otp_shield && (
            <p className="rounded-xl bg-primary-soft px-3 py-2 text-sm">
              OTP Shield: <strong>{t.otp_shield.risk_points} points</strong> → no OTP was sent; the customer was asked “Was this you?”. The
              payment check (R9) is the second safety net.
            </p>
          )}
          {result.steps.length > 1 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted">All {result.steps.length} payments in this story</summary>
              <ul className="mt-2 space-y-1">
                {result.steps.map((s, i) => (
                  <li key={s.txn_id} className="flex flex-wrap items-center gap-2">
                    <span className="num w-5 text-xs text-muted">{i + 1}.</span>
                    <span className="mono">{inr(s.amount)}</span>
                    <DecisionBadge status={s.status} />
                    {s.rules.map((c) => (
                      <RuleChip key={c} code={c} />
                    ))}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <Link to={`/app/transactions/${t.txn_id}`} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
            Open “why was this decided?” <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </motion.div>
  );
}

function LiveTraffic() {
  const [status, setStatus] = useState(null);
  const [rate, setRate] = useState(2);
  const [busy, setBusy] = useState(false);
  usePolling(async () => setStatus(await simulatorApi.status()), status?.running ? 2000 : 6000);

  const toggle = async () => {
    setBusy(true);
    try {
      const s = status?.running ? await simulatorApi.stop() : await simulatorApi.start(rate, 0.03);
      setStatus(s);
      toast.success(s.running ? 'Live traffic started — open the Live Monitor' : 'Live traffic stopped');
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Live traffic" subtitle="A steady stream of realistic payments (about 3% fraud) so the Live Monitor and Dashboard come alive.">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Button variant={status?.running ? 'danger' : 'primary'} icon={status?.running ? Square : Play} loading={busy} onClick={toggle}>
            {status?.running ? 'Stop live traffic' : 'Start live traffic'}
          </Button>
          <label className="flex items-center gap-2 text-sm text-muted">
            Speed
            <select className="input w-auto py-2" value={rate} onChange={(e) => setRate(Number(e.target.value))} disabled={status?.running}>
              <option value={1}>1 / second</option>
              <option value={2}>2 / second</option>
              <option value={5}>5 / second</option>
            </select>
          </label>
        </div>
        {status && (
          <dl className="grid grid-cols-4 gap-4 text-center text-xs">
            {[
              ['Sent', status.sent, 'text-ink'],
              ['Approved', status.approved, 'text-approved'],
              ['Held', status.review, 'text-review'],
              ['Blocked', status.blocked, 'text-blocked'],
            ].map(([label, value, cls]) => (
              <div key={label}>
                <dd className={clsx('num text-lg font-semibold', cls)}>{num(value)}</dd>
                <dt className="text-muted">{label}</dt>
              </div>
            ))}
          </dl>
        )}
      </div>
      <p className="mt-3 text-xs text-muted">
        Each demo customer pays at most once every 2½ minutes (real people don’t pay every few seconds), so with 200 customers the stream tops
        out around 2 payments a second.
      </p>
    </Card>
  );
}

export default function FraudLab() {
  const [running, setRunning] = useState(null);
  const [result, setResult] = useState(null);

  const run = async (code) => {
    setRunning(code);
    try {
      const res = await simulatorApi.run(code);
      setResult(res);
      if (res.expected_rule_fired) toast.success(res.summary);
      else toast.error(res.summary);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setRunning(null);
    }
  };

  return (
    <PageShell
      title="Fraud Lab"
      subtitle="Press a button to play out a real fraud story. It goes through the real API and the real SQL rules — watch which check catches it."
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SCENARIOS.map((s) => {
            const Icon = s.icon;
            const isNormal = s.code === 'NORMAL';
            return (
              <motion.button
                key={s.code}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                disabled={!!running}
                onClick={() => run(s.code)}
                className={clsx(
                  'card flex items-start gap-3 p-4 text-left transition hover:shadow-glow disabled:opacity-60',
                  isNormal && 'sm:col-span-2',
                )}
              >
                <span className={clsx('rounded-2xl p-3', isNormal ? 'bg-approved-soft text-approved' : 'bg-primary-soft text-primary')}>
                  {running === s.code ? <Loader2 className="h-6 w-6 animate-spin" /> : <Icon className="h-6 w-6" aria-hidden />}
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-medium text-muted">{isNormal ? 'Baseline' : s.code}</span>
                  <span className="block font-semibold">{s.name}</span>
                  <span className="mt-1 block text-xs text-muted">{s.story}</span>
                </span>
              </motion.button>
            );
          })}
        </div>
        <div className="space-y-4">
          <AnimatePresence mode="wait">
            {result ? (
              <ResultCard result={result} />
            ) : (
              <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card flex min-h-[280px] flex-col items-center justify-center gap-2 p-8 text-center">
                <p className="font-medium">Pick a story on the left</p>
                <p className="max-w-sm text-sm text-muted">The result appears here: the decision, the risk score, which rules fired and how long it took.</p>
              </motion.div>
            )}
          </AnimatePresence>
          <LiveTraffic />
        </div>
      </div>
    </PageShell>
  );
}
