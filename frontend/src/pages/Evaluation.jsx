import clsx from 'clsx';
import { motion } from 'framer-motion';
import { CheckCircle2, Gauge, Play, XCircle } from 'lucide-react';
import { useCallback, useState } from 'react';
import toast from 'react-hot-toast';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { errorMessage } from '../api/client';
import { evaluationApi } from '../api/endpoints';
import ChartTooltip from '../components/charts/ChartTooltip';
import PageShell from '../components/layout/PageShell';
import AnimatedNumber from '../components/ui/AnimatedNumber';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';
import Skeleton from '../components/ui/Skeleton';
import usePolling from '../hooks/usePolling';
import { num, pct, shortDate } from '../utils/format';
import { RULES } from '../utils/ruleInfo';

const TARGET_TEXT = {
  recall: { label: 'Fraud caught (recall)', plain: 'Of all fraud, how much was stopped', fmt: (v) => pct(v), goal: (t) => `≥ ${pct(t, 0)}` },
  fpr: { label: 'False alarms (FPR)', plain: 'Of genuine payments, how many were wrongly flagged', fmt: (v) => pct(v, 2), goal: (t) => `≤ ${pct(t, 0)}` },
  p95_ms: { label: 'Speed (p95)', plain: '95% of decisions were faster than this', fmt: (v) => `${Number(v).toFixed(1)} ms`, goal: (t) => `≤ ${t} ms` },
  tps: { label: 'Throughput', plain: 'Payments checked per second', fmt: (v) => `${Number(v).toFixed(0)}/s`, goal: (t) => `≥ ${t}/s` },
};

function TargetTile({ k, t, delay }) {
  const meta = TARGET_TEXT[k];
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="card p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-muted">{meta.label}</p>
        <span
          className={clsx(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
            t.pass ? 'bg-approved-soft text-approved' : 'bg-blocked-soft text-blocked',
          )}
        >
          {t.pass ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
          {t.pass ? 'Target met' : 'Missed'}
        </span>
      </div>
      <p className="mt-2 text-2xl font-semibold">{meta.fmt(t.value)}</p>
      <p className="text-xs text-muted">
        target {meta.goal(t.target)} · {meta.plain}
      </p>
    </motion.div>
  );
}

function Confusion({ run }) {
  const cells = [
    { label: 'Fraud caught', sub: 'true positives', v: run.tp, cls: 'bg-approved-soft text-approved' },
    { label: 'Fraud missed', sub: 'false negatives', v: run.fn, cls: 'bg-blocked-soft text-blocked' },
    { label: 'False alarms', sub: 'false positives', v: run.fp, cls: 'bg-review-soft text-review' },
    { label: 'Genuine, passed', sub: 'true negatives', v: run.tn, cls: 'bg-surface2 text-ink' },
  ];
  return (
    <div>
      <div className="mb-2 grid grid-cols-[auto_1fr_1fr] gap-2 text-center text-xs text-muted">
        <span />
        <span>FraudShield said “suspicious”</span>
        <span>FraudShield said “fine”</span>
      </div>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-2">
        <span className="flex items-center text-xs text-muted [writing-mode:vertical-rl] rotate-180">Real fraud</span>
        {[cells[0], cells[1]].map((c) => (
          <div key={c.label} className={clsx('rounded-2xl p-4 text-center', c.cls)}>
            <p className="text-2xl font-semibold">
              <AnimatedNumber value={c.v} />
            </p>
            <p className="text-xs font-medium">{c.label}</p>
            <p className="text-[10px] opacity-70">{c.sub}</p>
          </div>
        ))}
        <span className="flex items-center text-xs text-muted [writing-mode:vertical-rl] rotate-180">Genuine</span>
        {[cells[2], cells[3]].map((c) => (
          <div key={c.label} className={clsx('rounded-2xl p-4 text-center', c.cls)}>
            <p className="text-2xl font-semibold">
              <AnimatedNumber value={c.v} />
            </p>
            <p className="text-xs font-medium">{c.label}</p>
            <p className="text-[10px] opacity-70">{c.sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Evaluation() {
  const [latest, setLatest] = useState(undefined);
  const [history, setHistory] = useState([]);
  const [progress, setProgress] = useState(null);
  const [size, setSize] = useState(2000);

  const load = useCallback(async () => {
    try {
      const [l, h, p] = await Promise.all([evaluationApi.latest(), evaluationApi.history(), evaluationApi.status()]);
      setLatest(l);
      setHistory(h.runs);
      setProgress(p);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, []);
  usePolling(load, progress?.running ? 1500 : 15000);

  const run = async () => {
    try {
      const res = await evaluationApi.run(size, 0.03);
      setProgress(res.progress);
      toast.success('Evaluation started — this takes a little while');
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const chart = history.map((r) => ({
    label: `#${r.id} · ${shortDate(r.run_at)}`,
    recall: +(r.recall * 100).toFixed(2),
    precision: +(r.precision * 100).toFixed(2),
    fpr: +(r.fpr * 100).toFixed(2),
  }));
  const running = progress?.running;

  return (
    <PageShell
      title="Evaluation"
      subtitle="How good are the rules? FraudShield makes a fresh set of labelled payments (3% fraud), runs them through the real engine, and counts what it got right."
      actions={
        <>
          <select className="input w-auto py-2" value={size} onChange={(e) => setSize(Number(e.target.value))} disabled={running} aria-label="Number of payments">
            {[1000, 2000, 5000].map((s) => (
              <option key={s} value={s}>
                {num(s)} payments
              </option>
            ))}
          </select>
          <Button icon={Play} loading={running} onClick={run}>
            {running ? 'Running…' : 'Run evaluation'}
          </Button>
        </>
      }
    >
      {running && (
        <div className="card mb-4 p-4">
          <div className="mb-2 flex justify-between text-sm">
            <span>Checking payments…</span>
            <span className="num text-muted">
              {num(progress.done)} / {num(progress.total)}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface2">
            <motion.div className="h-full bg-primary" animate={{ width: `${(100 * progress.done) / Math.max(1, progress.total)}%` }} />
          </div>
        </div>
      )}
      {progress?.error && <p className="mb-4 rounded-xl border border-blocked/30 bg-blocked-soft px-4 py-3 text-sm text-blocked">{progress.error}</p>}

      {latest === undefined ? (
        <Skeleton className="h-96" />
      ) : !latest ? (
        <Card>
          <EmptyState icon={Gauge} title="No evaluation yet" text="Press “Run evaluation” to measure recall, false alarms, speed and throughput." />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {['recall', 'fpr', 'p95_ms', 'tps'].map((k, i) => (
              <TargetTile key={k} k={k} t={latest.targets[k]} delay={i * 0.05} />
            ))}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="What it got right and wrong" subtitle={`Run #${latest.id} · ${num(latest.total)} labelled payments · ${latest.mode === 'API' ? 'over HTTP' : 'in-process'}`}>
              <Confusion run={latest} />
              <dl className="mt-4 grid grid-cols-3 gap-3 text-center text-sm">
                <div>
                  <dd className="num font-semibold">{pct(latest.precision)}</dd>
                  <dt className="text-xs text-muted">precision</dt>
                </div>
                <div>
                  <dd className="num font-semibold">{pct(latest.f1)}</dd>
                  <dt className="text-xs text-muted">F1 score</dt>
                </div>
                <div>
                  <dd className="num font-semibold">{latest.p50_ms.toFixed(1)} ms</dd>
                  <dt className="text-xs text-muted">median time</dt>
                </div>
              </dl>
            </Card>
            <Card title="Per rule" subtitle="Precision = when the rule fired, how often it was real fraud. Recall = how much of that story’s fraud was caught.">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="py-2 font-medium">Rule</th>
                      <th className="py-2 text-right font-medium">Fired</th>
                      <th className="py-2 text-right font-medium">Precision</th>
                      <th className="py-2 text-right font-medium">Story recall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.per_rule.map((r) => {
                      const s = latest.per_scenario.find((x) => x.scenario === r.rule_code);
                      return (
                        <tr key={r.rule_code} className="border-b border-line/60 last:border-0">
                          <td className="py-2">
                            <span className="num mr-2 text-xs text-muted">{r.rule_code}</span>
                            {RULES[r.rule_code].name}
                          </td>
                          <td className="num py-2 text-right">{r.hits}</td>
                          <td className="num py-2 text-right">{r.precision == null ? '—' : pct(r.precision, 0)}</td>
                          <td className="num py-2 text-right">{s?.recall == null ? '—' : `${pct(s.recall, 0)} (${s.caught}/${s.count})`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
          {chart.length > 1 && (
            <Card className="mt-4" title="Past runs" subtitle="Recall, precision and false-alarm rate (%) of each evaluation.">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={chart} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="label" hide />
                  <YAxis tickLine={false} axisLine={false} unit="%" domain={[0, 100]} width={48} />
                  <Tooltip content={<ChartTooltip format={(v) => `${v}%`} />} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="recall" name="Recall" stroke="#10B981" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="precision" name="Precision" stroke="#6366F1" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="fpr" name="False alarms" stroke="#EF4444" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}
        </>
      )}
    </PageShell>
  );
}
