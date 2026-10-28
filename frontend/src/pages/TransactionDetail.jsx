import { ArrowLeft, ArrowRight, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { errorMessage } from '../api/client';
import { txnApi } from '../api/endpoints';
import ChartTooltip from '../components/charts/ChartTooltip';
import PageShell from '../components/layout/PageShell';
import DecisionBadge from '../components/risk/DecisionBadge';
import PipelineAnimation from '../components/risk/PipelineAnimation';
import RiskGauge from '../components/risk/RiskGauge';
import WhyBlockedPanel from '../components/risk/WhyBlockedPanel';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';
import Skeleton from '../components/ui/Skeleton';
import { exactTime, inr, inrRound, shortDate, timeAgo } from '../utils/format';

const STATUS_COLORS = { APPROVED: '#10B981', REVIEW: '#F59E0B', BLOCKED: '#EF4444', PENDING: '#6366F1' };

function Fact({ label, children }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/60 py-2 last:border-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm">{children || '—'}</dd>
    </div>
  );
}

function HistoryChart({ history, currentId }) {
  const rows = history.map((h) => ({ ...h, label: shortDate(h.txn_time) }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={rows} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
        <XAxis dataKey="label" hide />
        <YAxis tickLine={false} axisLine={false} width={56} tickFormatter={(v) => inrRound(v)} />
        <Tooltip
          cursor={{ fill: 'rgb(var(--surface-2))' }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <ChartTooltip
                active
                label={`${payload[0].payload.label} · ${payload[0].payload.city}`}
                payload={[{ ...payload[0], name: payload[0].payload.status.toLowerCase(), color: STATUS_COLORS[payload[0].payload.status] }]}
                format={(v) => inr(v)}
              />
            ) : null
          }
        />
        <Bar dataKey="amount" radius={[4, 4, 0, 0]} maxBarSize={22}>
          {rows.map((r) => (
            <Cell
              key={r.id}
              fill={STATUS_COLORS[r.status]}
              fillOpacity={r.id === currentId ? 1 : 0.45}
              stroke={r.id === currentId ? 'rgb(var(--ink))' : 'none'}
              strokeWidth={r.id === currentId ? 1.5 : 0}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function TransactionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    txnApi.detail(id).then(setData).catch((err) => setError(errorMessage(err)));
  }, [id]);

  if (error) {
    return (
      <PageShell title="Payment details">
        <EmptyState title="We couldn't load this payment" text={error} />
      </PageShell>
    );
  }
  if (!data) {
    return (
      <PageShell title="Payment details">
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-72" />
          <Skeleton className="h-72 lg:col-span-2" />
        </div>
      </PageShell>
    );
  }

  const t = data.transaction;
  const counterparty = t.merchant_name ? `${t.merchant_name} (${t.merchant_category})` : t.payee_name ? `${t.payee_name} — payee` : 'Cash withdrawal';
  return (
    <PageShell
      title="Why was this decision made?"
      subtitle={`Payment ${t.external_ref} · ${timeAgo(t.txn_time)}`}
      actions={
        <>
          <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(-1)}>
            Back
          </Button>
          {data.alert?.case_id && (
            <Link to={`/app/cases/${data.alert.case_id}`}>
              <Button size="sm" icon={ArrowRight}>
                Open case
              </Button>
            </Link>
          )}
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:row-span-2" bodyClass="flex flex-col items-center gap-4 p-6 text-center">
          <DecisionBadge status={t.status} size="lg" />
          <RiskGauge score={t.risk_score} bands={data.bands} />
          <p className="num text-3xl font-semibold">{inr(t.amount)}</p>
          <div className="space-y-1">
            <p className="font-medium">{data.explanation.headline}</p>
            <p className="text-sm text-muted">{data.explanation.reason}</p>
            <p className="text-sm text-muted">Next: {data.explanation.next_step}</p>
          </div>
          <dl className="mt-2 w-full text-left">
            <Fact label="Customer">{t.customer_name}</Fact>
            <Fact label="Account">
              <span className="mono">{t.account_no}</span>
            </Fact>
            <Fact label="Paid to">{counterparty}</Fact>
            <Fact label="Channel">{t.channel}</Fact>
            <Fact label="City">
              {t.city} {t.home_city && t.city !== t.home_city && <span className="text-xs text-muted">(lives in {t.home_city})</span>}
            </Fact>
            <Fact label="Device">
              <span className="mono text-xs">{t.device_id}</span>
            </Fact>
            <Fact label="Internet address">
              <span className="mono text-xs">{t.ip_address}</span>
            </Fact>
            <Fact label="Time">{exactTime(t.txn_time)}</Fact>
            <Fact label="Decided in">{t.decision_ms != null ? `${Number(t.decision_ms).toFixed(1)} ms` : 'historic payment'}</Fact>
          </dl>
        </Card>

        <Card className="lg:col-span-2" title="The checks, in plain English" subtitle="What FraudShield looked at and what it found.">
          <WhyBlockedPanel rules={data.rules} />
          {data.otp_request && (
            <div className="mt-5 rounded-2xl border border-primary/30 bg-primary-soft p-4">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <ShieldCheck className="h-4 w-4 text-primary" aria-hidden /> OTP Shield checked this payment first
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {(data.otp_request.signals_json || []).map((s) => (
                  <li key={s.code} className="flex justify-between gap-3">
                    <span>{s.text}</span>
                    <span className="num text-muted">+{s.points}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card className="lg:col-span-2" title="How it was decided" subtitle="The six stages inside FraudShield, with the real time each one took.">
          <PipelineAnimation timings={t.stage_timings} status={t.status} />
        </Card>
      </div>

      <Card className="mt-4" title="This account's recent payments" subtitle="This payment is outlined; colours show each decision. Hover a bar for details.">
        <HistoryChart history={data.history} currentId={t.id} />
      </Card>
    </PageShell>
  );
}
