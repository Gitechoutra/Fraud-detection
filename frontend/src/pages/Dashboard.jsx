import { motion } from 'framer-motion';
import { Activity, CheckCircle2, IndianRupee, PauseCircle, ShieldX, Timer } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { errorMessage } from '../api/client';
import { dashboardApi } from '../api/endpoints';
import ChartTooltip from '../components/charts/ChartTooltip';
import CityMap from '../components/charts/CityMap';
import FraudByChannel from '../components/charts/FraudByChannel';
import RuleHitsChart from '../components/charts/RuleHitsChart';
import VolumeChart from '../components/charts/VolumeChart';
import PageShell from '../components/layout/PageShell';
import AnimatedNumber from '../components/ui/AnimatedNumber';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';
import Skeleton from '../components/ui/Skeleton';
import Tabs from '../components/ui/Tabs';
import usePolling from '../hooks/usePolling';
import { inrShort, pct } from '../utils/format';

const RANGES = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
];
const DECISION_COLORS = { APPROVED: '#10B981', REVIEW: '#F59E0B', BLOCKED: '#EF4444' };
const DECISION_NAMES = { APPROVED: 'Approved', REVIEW: 'Held for review', BLOCKED: 'Blocked' };

function Kpi({ icon: Icon, label, value, format, hint, tone = 'text-primary', delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="card p-4"
    >
      <div className="flex items-center gap-2 text-xs font-medium text-muted">
        <Icon className={`h-4 w-4 ${tone}`} aria-hidden />
        {label}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight">
        <AnimatedNumber value={value} format={format} />
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </motion.div>
  );
}

function DecisionsDonut({ data }) {
  const rows = data.map((d) => ({ ...d, name: DECISION_NAMES[d.status] }));
  const total = rows.reduce((a, b) => a + b.value, 0);
  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative h-44 w-44 shrink-0">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="100%" stroke="rgb(var(--surface))" strokeWidth={2} paddingAngle={1}>
              {rows.map((r) => (
                <Cell key={r.status} fill={DECISION_COLORS[r.status]} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="num text-xl font-semibold">{total.toLocaleString('en-IN')}</span>
          <span className="text-[11px] text-muted">payments</span>
        </div>
      </div>
      <ul className="w-full space-y-2 text-sm">
        {['APPROVED', 'REVIEW', 'BLOCKED'].map((s) => {
          const v = rows.find((r) => r.status === s)?.value || 0;
          return (
            <li key={s} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 whitespace-nowrap">
                <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: DECISION_COLORS[s] }} />
                {DECISION_NAMES[s]}
              </span>
              <span className="num whitespace-nowrap text-xs text-muted">
                {v.toLocaleString('en-IN')} · {total ? pct(v / total) : '0%'}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function Dashboard() {
  const [range, setRange] = useState('today');
  const [summary, setSummary] = useState(null);
  const [charts, setCharts] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([dashboardApi.summary(range), dashboardApi.charts(range)]);
      setSummary(s);
      setCharts(c);
      setError('');
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [range]);

  usePolling(load, 15000);

  const changeRange = (r) => {
    setRange(r);
    setSummary(null);
    setCharts(null);
  };

  return (
    <PageShell
      title="Dashboard"
      subtitle="How many payments were checked, how many were stopped, and why — updated every 15 seconds."
      actions={<Tabs id="range" tabs={RANGES} value={range} onChange={changeRange} />}
    >
      {error && <p className="mb-4 rounded-xl border border-blocked/30 bg-blocked-soft px-4 py-3 text-sm text-blocked">{error}</p>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {!summary
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[104px]" />)
          : [
              { icon: Activity, label: range === 'today' ? 'Payments today' : 'Payments', value: summary.total, hint: `${pct(summary.flag_rate)} flagged` },
              { icon: CheckCircle2, label: 'Approved', value: summary.approved, tone: 'text-approved', hint: 'went through normally' },
              { icon: PauseCircle, label: 'Held for review', value: summary.review, tone: 'text-review', hint: `${summary.open_alerts} alerts open` },
              { icon: ShieldX, label: 'Blocked', value: summary.blocked, tone: 'text-blocked', hint: 'money never left' },
              { icon: IndianRupee, label: 'Money protected', value: summary.money_protected, format: inrShort, tone: 'text-approved', hint: 'value of blocked payments' },
              {
                icon: Timer,
                label: 'Avg decision time',
                value: summary.avg_decision_ms || 0,
                format: (v) => `${v.toFixed(1)} ms`,
                hint: summary.avg_decision_ms ? 'from receipt to decision' : 'no live payments yet',
              },
            ].map((k, i) => <Kpi key={k.label} {...k} delay={i * 0.04} />)}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Payments over time" subtitle="Each bar shows how many payments were approved, held or blocked.">
          {!charts ? <Skeleton className="h-64" /> : charts.volume.length ? <VolumeChart data={charts.volume} /> : <EmptyState title="No payments in this period" />}
        </Card>
        <Card title="Decisions" subtitle="Share of each outcome.">
          {!charts ? <Skeleton className="h-44" /> : <DecisionsDonut data={charts.decisions} />}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Flagged by payment type" subtitle="Percentage of each channel’s payments that were held or blocked.">
          {!charts ? <Skeleton className="h-52" /> : <FraudByChannel data={charts.by_channel} />}
        </Card>
        <Card title="Top cities" subtitle="Bigger dot = more payments; red = held or blocked.">
          {!charts ? <Skeleton className="h-52" /> : <CityMap data={charts.cities} />}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="How often each rule fired" subtitle="Number of payments each warning sign was found in.">
          {!charts ? <Skeleton className="h-56" /> : <RuleHitsChart data={charts.rule_hits} />}
        </Card>
        <Card title="How often each rule is right" subtitle="Of the cases analysts closed, the share confirmed as real fraud (all time).">
          {!charts ? <Skeleton className="h-56" /> : <RuleHitsChart data={charts.rule_precision} valueKey="precision" />}
        </Card>
      </div>
    </PageShell>
  );
}
