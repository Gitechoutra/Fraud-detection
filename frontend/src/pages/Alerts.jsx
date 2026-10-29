import { BellOff, BellRing, Search, UserCheck } from 'lucide-react';
import { useCallback, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { alertApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import CustomerResponseBadge from '../components/risk/CustomerResponseBadge';
import DecisionBadge from '../components/risk/DecisionBadge';
import RuleChip from '../components/risk/RuleChip';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Table, { Pager } from '../components/ui/Table';
import Tabs from '../components/ui/Tabs';
import Tooltip from '../components/ui/Tooltip';
import usePolling from '../hooks/usePolling';
import { ALERT_POLL_MS } from '../utils/polling';
import { exactTime, inr, timeAgo, titleCase } from '../utils/format';

export default function Alerts() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('OPEN');
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [res, setRes] = useState(null);
  const [busyId, setBusyId] = useState(null);
  // Alerts that appeared while this page was open (newest first).
  const [justIn, setJustIn] = useState([]);
  const known = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await alertApi.list({ status, page, per_page: 15, search: search || undefined, mine: mine ? 1 : undefined });
      setRes(r);
      const ids = r.newest.map((a) => a.alert_id);
      if (known.current === null) {
        known.current = new Set(ids); // what was already there when the page opened
      } else {
        const fresh = r.newest.filter((a) => !known.current.has(a.alert_id));
        if (fresh.length) {
          fresh.forEach((a) => known.current.add(a.alert_id));
          setJustIn((prev) => [...fresh, ...prev].slice(0, 5));
          // Measured freshness: the server stamps when each one was first shown.
          alertApi.seen(fresh.map((a) => a.alert_id)).catch(() => {});
        }
      }
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [status, page, search, mine]);
  usePolling(load, ALERT_POLL_MS);

  const assign = async (e, row) => {
    e.stopPropagation();
    setBusyId(row.alert_id);
    try {
      await alertApi.update(row.alert_id, { assign_to_me: true });
      toast.success(`Alert #${row.alert_id} is now yours`);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const columns = [
    {
      key: 'priority',
      label: 'Priority',
      render: (r) => <Badge tone={r.priority === 'HIGH' ? 'blocked' : 'review'}>{r.priority === 'HIGH' ? 'High' : 'Medium'}</Badge>,
    },
    {
      key: 'summary',
      label: 'What happened',
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{r.customer_name || 'Unknown customer'}</p>
          <p className="truncate text-xs text-muted">{r.summary}</p>
        </div>
      ),
    },
    { key: 'amount', label: 'Amount', className: 'text-right', render: (r) => <span className="mono">{inr(r.amount)}</span> },
    {
      key: 'decision',
      label: 'Decision',
      hideOnMobile: true,
      render: (r) => (r.txn_status ? <DecisionBadge status={r.txn_status} /> : <Badge tone="primary">OTP Shield</Badge>),
    },
    {
      key: 'rules',
      label: 'Signs',
      hideOnMobile: true,
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {r.rule_codes.length ? r.rule_codes.map((c) => <RuleChip key={c} code={c} />) : <span className="text-xs text-muted">Customer said NO</span>}
        </div>
      ),
    },
    {
      key: 'customer',
      label: 'Customer says',
      hideOnMobile: true,
      render: (r) => (r.txn_id ? <CustomerResponseBadge response={r.customer_response} /> : <span className="text-xs text-muted">—</span>),
    },
    {
      key: 'age',
      label: 'Waiting',
      render: (r) => (
        <Tooltip text={exactTime(r.created_at)}>
          <span className="text-xs text-muted">{timeAgo(r.created_at)}</span>
        </Tooltip>
      ),
    },
    {
      key: 'owner',
      label: 'Owner',
      render: (r) =>
        r.alert_status === 'CLOSED' ? (
          <span className="text-xs text-muted">{r.outcome ? titleCase(r.outcome) : 'Closed'}</span>
        ) : r.assigned_name ? (
          <span className="text-xs">{r.assigned_name}</span>
        ) : (
          <Button size="sm" variant="secondary" icon={UserCheck} loading={busyId === r.alert_id} onClick={(e) => assign(e, r)}>
            Assign to me
          </Button>
        ),
    },
  ];

  const counts = res?.counts || {};
  return (
    <PageShell
      title="Alerts"
      subtitle="Payments that were held or blocked, oldest and most urgent first. Open one to investigate and decide."
    >
      {justIn.length > 0 && (
        <div className="card mb-4 p-4" aria-live="polite">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-sm font-medium">
              <BellRing className="h-4 w-4 text-blocked" aria-hidden /> Just in
            </p>
            <button type="button" className="text-xs text-muted underline" onClick={() => setJustIn([])}>
              Clear
            </button>
          </div>
          <ul className="space-y-1.5">
            {justIn.map((a) => (
              <li key={a.alert_id}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1 text-left text-sm hover:bg-surface2"
                  onClick={() => a.case_id && navigate(`/app/cases/${a.case_id}`)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Badge tone={a.priority === 'HIGH' ? 'blocked' : 'review'}>{a.priority === 'HIGH' ? 'High' : 'Medium'}</Badge>
                    <span className="truncate">{a.summary}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted" title={exactTime(a.created_at)}>
                    {timeAgo(a.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Card bodyClass="p-4">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <Tabs
            id="alert-status"
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            tabs={[
              { value: 'OPEN', label: 'New', count: counts.OPEN },
              { value: 'IN_PROGRESS', label: 'In progress', count: counts.IN_PROGRESS },
              { value: 'CLOSED', label: 'Closed', count: counts.CLOSED },
              { value: 'ALL', label: 'All' },
            ]}
          />
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="accent-primary" />
              Only mine
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
              <input
                className="input pl-9 sm:w-64"
                placeholder="Search name or account"
                aria-label="Search alerts"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
        </div>
        <Table
          rowKey="alert_id"
          columns={columns}
          rows={res?.items}
          loading={!res}
          onRowClick={(r) => navigate(`/app/cases/${r.case_id}`)}
          empty={{ icon: BellOff, title: 'No alerts here', text: 'When a payment is held or blocked, it shows up in this list within seconds.' }}
        />
        <Pager page={res?.page} pages={res?.pages} onPage={setPage} />
      </Card>
    </PageShell>
  );
}
