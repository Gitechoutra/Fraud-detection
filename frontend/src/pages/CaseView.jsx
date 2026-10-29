import { ArrowLeft, CheckCircle2, ExternalLink, MessageSquarePlus, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useCallback, useState } from 'react';
import toast from 'react-hot-toast';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { alertApi, caseApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import CustomerResponseBadge from '../components/risk/CustomerResponseBadge';
import DecisionBadge from '../components/risk/DecisionBadge';
import RiskGauge from '../components/risk/RiskGauge';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';
import Modal from '../components/ui/Modal';
import Skeleton from '../components/ui/Skeleton';
import usePolling from '../hooks/usePolling';
import { exactTime, inr, shortDate, timeAgo } from '../utils/format';
import { ALERT_POLL_MS } from '../utils/polling';
import { RULES } from '../utils/ruleInfo';

const FUNDS_TEXT = {
  DEBITED: 'debited from the account',
  HELD: 'held — not paid until the customer confirms',
  PAID_AFTER_REVIEW: 'paid after the customer confirmed',
  RELEASED: 'hold released, nothing paid',
  NOT_MOVED: 'no money moved',
};

export default function CaseView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [closing, setClosing] = useState(null);
  const [closeNote, setCloseNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => caseApi.get(id).then(setData).catch((err) => setError(errorMessage(err))), [id]);
  // Re-read so the customer's answer in the banking app shows up live.
  usePolling(load, ALERT_POLL_MS);

  const addNote = async (e) => {
    e.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    try {
      await caseApi.addNote(id, note.trim());
      setNote('');
      toast.success('Note added');
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const takeCase = async () => {
    try {
      await alertApi.update(data.alert.alert_id, { assign_to_me: true });
      toast.success('You are now working on this case');
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const close = async () => {
    setBusy(true);
    try {
      await caseApi.close(id, closing, closeNote.trim() || undefined);
      toast.success(closing === 'CONFIRMED_FRAUD' ? 'Case closed as fraud' : 'Case closed as genuine');
      setClosing(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <PageShell title="Case">
        <EmptyState title="We couldn't load this case" text={error} />
      </PageShell>
    );
  }
  if (!data) {
    return (
      <PageShell title="Case">
        <Skeleton className="h-96" />
      </PageShell>
    );
  }

  const { case: c, alert: a } = data;
  const open = !c.outcome;
  return (
    <PageShell
      title={`Case #${c.id}`}
      subtitle={`${a.customer_name || 'Customer'} · ${a.summary}`}
      actions={
        <>
          <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/app/alerts')}>
            Alerts
          </Button>
          {open && !a.assigned_to && (
            <Button variant="secondary" size="sm" onClick={takeCase}>
              Assign to me
            </Button>
          )}
          {open && (
            <>
              <Button variant="danger" size="sm" icon={ShieldAlert} onClick={() => setClosing('CONFIRMED_FRAUD')}>
                Confirm fraud
              </Button>
              <Button variant="success" size="sm" icon={ShieldCheck} onClick={() => setClosing('FALSE_POSITIVE')}>
                Mark as genuine
              </Button>
            </>
          )}
        </>
      }
    >
      {!open && (
        <div
          className={`mb-4 flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm ${
            c.outcome === 'CONFIRMED_FRAUD' ? 'border-blocked/30 bg-blocked-soft' : 'border-approved/30 bg-approved-soft'
          }`}
        >
          <CheckCircle2 className="h-4 w-4" aria-hidden />
          Closed {timeAgo(c.closed_at)} by {c.analyst || 'an analyst'} as{' '}
          <strong>{c.outcome === 'CONFIRMED_FRAUD' ? 'confirmed fraud' : 'genuine (false alarm)'}</strong>.
          {c.notes && <span className="text-muted">“{c.notes}”</span>}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="The payment" bodyClass="flex flex-col items-center gap-3 p-5 text-center">
          {a.txn_status ? <DecisionBadge status={a.txn_status} size="lg" /> : <Badge tone="primary">Stopped by OTP Shield</Badge>}
          <RiskGauge score={a.risk_score} />
          <p className="num text-2xl font-semibold">{inr(a.amount)}</p>
          <p className="text-sm text-muted">
            {a.channel || 'Net banking'} · {a.city} · {shortDate(a.txn_time || a.created_at)}
          </p>
          <Badge tone={a.priority === 'HIGH' ? 'blocked' : 'review'}>{a.priority === 'HIGH' ? 'High priority' : 'Medium priority'}</Badge>
          {a.txn_id && <CustomerResponseBadge response={a.customer_response} withHelp />}
          {a.funds_status && <p className="text-xs text-muted">Money: {FUNDS_TEXT[a.funds_status]}</p>}
          {a.txn_id && (
            <Link to={`/app/transactions/${a.txn_id}`} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
              Full explanation <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          )}
          <p className="text-xs text-muted">Account <span className="mono">{a.account_no}</span></p>
        </Card>

        <Card className="lg:col-span-2" title="Evidence" subtitle="The warning signs that raised this alert.">
          {data.hits.length > 0 ? (
            <ul className="space-y-3">
              {data.hits.map((h) => {
                const info = RULES[h.rule_code];
                const Icon = info?.icon;
                return (
                  <li key={h.rule_code} className="flex gap-3 rounded-2xl border border-line bg-surface2/50 p-3">
                    {Icon && <Icon className="mt-0.5 h-5 w-5 shrink-0 text-blocked" aria-hidden />}
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center justify-between gap-2 text-sm font-semibold">
                        {info?.name}
                        <span className="num text-xs text-muted">+{h.weight_applied}</span>
                      </p>
                      <p className="text-sm">{h.detail_text}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : data.otp_request ? (
            <div>
              <p className="mb-3 text-sm">
                Someone tried to pay {inr(data.otp_request.amount)} from device{' '}
                <span className="mono text-xs">{data.otp_request.requesting_device_id}</span> in {data.otp_request.city}. OTP Shield sent no
                OTP and asked the customer — who said <strong>NO</strong>.
              </p>
              <ul className="space-y-1.5 text-sm">
                {(data.otp_request.signals_json || []).map((s) => (
                  <li key={s.code} className="flex justify-between gap-3 rounded-xl bg-surface2/60 px-3 py-2">
                    <span>{s.text}</span>
                    <span className="num text-muted">+{s.points}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <EmptyState title="No evidence recorded" />
          )}
        </Card>

        <Card title="Timeline">
          <ol className="relative space-y-4 border-l border-line pl-5">
            {data.timeline.map((e, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full bg-primary ring-4 ring-surface" />
                <p className="text-sm">{e.text}</p>
                <p className="text-xs text-muted" title={exactTime(e.at)}>
                  {timeAgo(e.at)}
                </p>
              </li>
            ))}
          </ol>
        </Card>

        <Card className="lg:col-span-2" title="Notes" subtitle="What you found out — calls made, what the customer said.">
          <ul className="mb-4 space-y-2">
            {data.notes.length === 0 && <li className="text-sm text-muted">No notes yet.</li>}
            {data.notes.map((n) => (
              <li key={n.id} className="rounded-xl bg-surface2/60 px-3 py-2">
                <p className="text-sm">{n.body}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {n.author} · {timeAgo(n.created_at)}
                </p>
              </li>
            ))}
          </ul>
          {open && (
            <form onSubmit={addNote} className="flex flex-col gap-2 sm:flex-row">
              <input className="input" placeholder="Add a note…" value={note} onChange={(e) => setNote(e.target.value)} aria-label="New note" />
              <Button type="submit" icon={MessageSquarePlus} loading={busy} disabled={!note.trim()}>
                Add
              </Button>
            </form>
          )}
        </Card>
      </div>

      <Card className="mt-4" title="Recent payments on this account">
        <ul className="divide-y divide-line">
          {data.recent_transactions.map((t) => (
            <li key={t.id}>
              <Link to={`/app/transactions/${t.id}`} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-primary">
                <span className="text-xs text-muted">{shortDate(t.txn_time)}</span>
                <span className="hidden text-xs text-muted sm:inline">
                  {t.channel} · {t.city}
                </span>
                <span className="mono">{inr(t.amount)}</span>
                <DecisionBadge status={t.status} />
              </Link>
            </li>
          ))}
        </ul>
      </Card>

      <Modal
        open={!!closing}
        onClose={() => setClosing(null)}
        title={closing === 'CONFIRMED_FRAUD' ? 'Close as confirmed fraud?' : 'Close as genuine?'}
        footer={
          <>
            <Button variant="ghost" onClick={() => setClosing(null)}>
              Cancel
            </Button>
            <Button variant={closing === 'CONFIRMED_FRAUD' ? 'danger' : 'success'} loading={busy} onClick={close}>
              Close case
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          {closing === 'CONFIRMED_FRAUD'
            ? 'This tells FraudShield its warning signs were right. It improves the rule accuracy numbers.'
            : 'This records a false alarm: the customer really made this payment. It lowers the accuracy of the rules that fired.'}
        </p>
        <label className="label mt-4" htmlFor="close-note">
          Closing note (optional)
        </label>
        <textarea id="close-note" className="input min-h-[90px]" value={closeNote} onChange={(e) => setCloseNote(e.target.value)} />
      </Modal>
    </PageShell>
  );
}
