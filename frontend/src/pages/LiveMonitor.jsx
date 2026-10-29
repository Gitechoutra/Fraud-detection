import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import { Pause, Play, Radio } from 'lucide-react';
import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { simulatorApi, txnApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import DecisionBadge from '../components/risk/DecisionBadge';
import RiskGauge from '../components/risk/RiskGauge';
import RuleChip from '../components/risk/RuleChip';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';
import Skeleton from '../components/ui/Skeleton';
import Tabs from '../components/ui/Tabs';
import Tooltip from '../components/ui/Tooltip';
import usePolling from '../hooks/usePolling';
import { ALERT_POLL_MS } from '../utils/polling';
import { exactTime, inr, shortTime, timeAgo } from '../utils/format';

const MAX_ROWS = 120;
const STATUS_TABS = [
  { value: 'ALL', label: 'All' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REVIEW', label: 'Held' },
  { value: 'BLOCKED', label: 'Blocked' },
];
const CHANNELS = ['ALL', 'UPI', 'CARD', 'NETBANKING', 'ATM'];

function rowMotion(status) {
  return {
    initial: { opacity: 0, y: -16 },
    animate: {
      opacity: 1,
      y: 0,
      backgroundColor: status === 'BLOCKED' ? ['rgba(239,68,68,0.28)', 'rgba(239,68,68,0)'] : 'rgba(0,0,0,0)',
    },
    transition: { duration: status === 'BLOCKED' ? 1.4 : 0.3 },
  };
}

export default function LiveMonitor() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [paused, setPaused] = useState(false);
  const [status, setStatus] = useState('ALL');
  const [channel, setChannel] = useState('ALL');
  const [stream, setStream] = useState(null);
  const [error, setError] = useState('');
  const lastId = useRef(0);

  const poll = useCallback(async () => {
    try {
      const res = await txnApi.latest(lastId.current || undefined);
      if (res.items.length) {
        lastId.current = Math.max(lastId.current, res.items[res.items.length - 1].id);
        // De-duplicate: two overlapping polls (e.g. StrictMode's double mount) can return the same rows.
        setRows((prev) => {
          const seen = new Set(prev.map((r) => r.id));
          const fresh = res.items.filter((r) => !seen.has(r.id)).reverse();
          return fresh.length ? [...fresh, ...prev].slice(0, MAX_ROWS) : prev;
        });
      }
      setLoaded(true);
      setError('');
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);
  usePolling(poll, ALERT_POLL_MS, !paused);
  usePolling(async () => setStream(await simulatorApi.status()), 5000);

  const visible = useMemo(
    () => rows.filter((r) => (status === 'ALL' || r.status === status) && (channel === 'ALL' || r.channel === channel)),
    [rows, status, channel],
  );
  const counts = useMemo(() => {
    const c = { ALL: rows.length, APPROVED: 0, REVIEW: 0, BLOCKED: 0 };
    rows.forEach((r) => (c[r.status] = (c[r.status] || 0) + 1));
    return c;
  }, [rows]);

  return (
    <PageShell
      title="Live monitor"
      subtitle="Every payment appears here within seconds of being checked. Click one to see exactly why it was approved, held or blocked."
      actions={
        <>
          <span
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs',
              paused ? 'border-line text-muted' : 'border-approved/30 bg-approved-soft text-approved',
            )}
          >
            <Radio className={clsx('h-3.5 w-3.5', !paused && 'animate-pulse')} aria-hidden />
            {paused ? 'Paused' : 'Live'}
            {stream?.running && ' · traffic generator on'}
          </span>
          <Button variant="secondary" size="sm" icon={paused ? Play : Pause} onClick={() => setPaused((p) => !p)}>
            {paused ? 'Resume' : 'Pause'}
          </Button>
        </>
      }
    >
      {error && <p className="mb-4 rounded-xl border border-blocked/30 bg-blocked-soft px-4 py-3 text-sm text-blocked">{error}</p>}
      <Card bodyClass="p-0 sm:p-0">
        <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center sm:justify-between">
          <Tabs id="live-status" tabs={STATUS_TABS.map((t) => ({ ...t, count: counts[t.value] }))} value={status} onChange={setStatus} />
          <label className="flex items-center gap-2 text-xs text-muted">
            Channel
            <select className="input w-auto py-1.5" value={channel} onChange={(e) => setChannel(e.target.value)}>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {c === 'ALL' ? 'All' : c}
                </option>
              ))}
            </select>
          </label>
        </div>

        {!loaded ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : !visible.length ? (
          <EmptyState
            icon={Radio}
            title="Waiting for payments"
            text="New payments will slide in here. Start the traffic generator in the Fraud Lab to see a steady stream."
          />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-4 py-2.5 font-medium">Time</th>
                    <th className="px-3 py-2.5 font-medium">Customer</th>
                    <th className="px-3 py-2.5 text-right font-medium">Amount</th>
                    <th className="px-3 py-2.5 font-medium">Channel</th>
                    <th className="px-3 py-2.5 font-medium">City</th>
                    <th className="px-3 py-2.5 font-medium">Risk</th>
                    <th className="px-3 py-2.5 font-medium">Decision</th>
                    <th className="px-4 py-2.5 font-medium">Warning signs</th>
                  </tr>
                </thead>
                <tbody>
                  <AnimatePresence initial={false}>
                    {visible.map((r) => (
                      <motion.tr
                        key={r.id}
                        layout="position"
                        {...rowMotion(r.status)}
                        onClick={() => navigate(`/app/transactions/${r.id}`)}
                        onKeyDown={(e) => e.key === 'Enter' && navigate(`/app/transactions/${r.id}`)}
                        tabIndex={0}
                        className="cursor-pointer border-b border-line/60 hover:bg-surface2/70"
                      >
                        <td className="px-4 py-2">
                          <Tooltip text={exactTime(r.txn_time)}>
                            <span className="mono text-xs">{shortTime(r.txn_time)}</span>
                          </Tooltip>
                        </td>
                        <td className="max-w-[180px] truncate px-3 py-2">{r.customer_name}</td>
                        <td className="mono px-3 py-2 text-right">{inr(r.amount)}</td>
                        <td className="px-3 py-2 text-xs text-muted">{r.channel}</td>
                        <td className="px-3 py-2 text-xs">{r.city}</td>
                        <td className="px-3 py-1">
                          <RiskGauge score={r.risk_score} size="sm" />
                        </td>
                        <td className="px-3 py-2">
                          <DecisionBadge status={r.status} />
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex flex-wrap gap-1">
                            {r.rule_codes.length ? r.rule_codes.map((c) => <RuleChip key={c} code={c} />) : <span className="text-xs text-muted">none</span>}
                          </div>
                        </td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
            <ul className="divide-y divide-line md:hidden">
              <AnimatePresence initial={false}>
                {visible.map((r) => (
                  <motion.li key={r.id} layout="position" {...rowMotion(r.status)} onClick={() => navigate(`/app/transactions/${r.id}`)} className="cursor-pointer p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{r.customer_name}</span>
                      <span className="mono shrink-0">{inr(r.amount)}</span>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-xs text-muted">
                        {timeAgo(r.txn_time)} · {r.channel} · {r.city}
                      </span>
                      <DecisionBadge status={r.status} />
                    </div>
                    {r.rule_codes.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {r.rule_codes.map((c) => (
                          <RuleChip key={c} code={c} />
                        ))}
                      </div>
                    )}
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          </>
        )}
      </Card>
    </PageShell>
  );
}
