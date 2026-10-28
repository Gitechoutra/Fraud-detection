import { ListX, Plus, Search, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { errorMessage } from '../api/client';
import { watchlistApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Modal from '../components/ui/Modal';
import Table, { Pager } from '../components/ui/Table';
import useAuth from '../hooks/useAuth';
import { exactTime, timeAgo } from '../utils/format';

const TYPES = { IP: 'Internet address', DEVICE: 'Device', ACCOUNT: 'Bank account', MERCHANT: 'Shop (id or name)' };

export default function Watchlist() {
  const { hasRole } = useAuth();
  const canEdit = hasRole('RISK_MANAGER');
  const [res, setRes] = useState(null);
  const [type, setType] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ entry_type: 'IP', entry_value: '', reason: '' });
  const [removing, setRemoving] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      watchlistApi
        .list({ type: type || undefined, search: search || undefined, page })
        .then(setRes)
        .catch((err) => toast.error(errorMessage(err))),
    [type, search, page],
  );
  useEffect(() => {
    load();
  }, [load]);

  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await watchlistApi.add(form);
      toast.success('Added to the watchlist — rule R6 uses it from the next payment');
      setAdding(false);
      setForm({ entry_type: 'IP', entry_value: '', reason: '' });
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await watchlistApi.remove(removing.id);
      toast.success('Removed from the watchlist');
      setRemoving(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: 'entry_type', label: 'Type', render: (r) => <Badge tone="blocked">{TYPES[r.entry_type]}</Badge> },
    { key: 'entry_value', label: 'Value', render: (r) => <span className="mono break-all text-xs">{r.entry_value}</span> },
    { key: 'reason', label: 'Why it is listed', render: (r) => <span className="text-sm">{r.reason}</span> },
    { key: 'added_by', label: 'Added by', hideOnMobile: true },
    { key: 'added_at', label: 'When', render: (r) => <span className="text-xs text-muted" title={exactTime(r.added_at)}>{timeAgo(r.added_at)}</span> },
    ...(canEdit
      ? [
          {
            key: 'actions',
            label: '',
            className: 'text-right',
            render: (r) => (
              <button onClick={() => setRemoving(r)} className="rounded-lg p-1.5 text-muted hover:bg-blocked-soft hover:text-blocked" aria-label={`Remove ${r.entry_value}`}>
                <Trash2 className="h-4 w-4" />
              </button>
            ),
          },
        ]
      : []),
  ];

  return (
    <PageShell
      title="Watchlist"
      subtitle="Phones, internet addresses, accounts and shops already linked to fraud. Any payment that touches one of them is flagged by rule R6."
      actions={canEdit && <Button icon={Plus} onClick={() => setAdding(true)}>Add entry</Button>}
    >
      <Card bodyClass="p-4">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row">
          <select className="input sm:w-56" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Filter by type">
            <option value="">All types</option>
            {Object.entries(TYPES).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input className="input pl-9" placeholder="Search value or reason" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} aria-label="Search watchlist" />
          </div>
        </div>
        <Table columns={columns} rows={res?.items} loading={!res} empty={{ icon: ListX, title: 'Nothing on the watchlist', text: 'Entries appear here when added by a risk manager or when a customer answers NO in OTP Shield.' }} />
        <Pager page={res?.page} pages={res?.pages} onPage={setPage} />
      </Card>

      <Modal open={adding} onClose={() => setAdding(false)} title="Add to the watchlist">
        <form onSubmit={add} className="space-y-3">
          <div>
            <label className="label" htmlFor="wl-type">Type</label>
            <select id="wl-type" className="input" value={form.entry_type} onChange={(e) => setForm({ ...form, entry_type: e.target.value })}>
              {Object.entries(TYPES).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="wl-value">Value</label>
            <input id="wl-value" className="input num" required value={form.entry_value} onChange={(e) => setForm({ ...form, entry_value: e.target.value })} placeholder="e.g. 185.220.101.4" />
          </div>
          <div>
            <label className="label" htmlFor="wl-reason">Reason</label>
            <input id="wl-reason" className="input" required minLength={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="e.g. Reported by customer in a scam call" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Add</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title="Remove from the watchlist?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button>
            <Button variant="danger" loading={busy} onClick={remove}>Remove</Button>
          </>
        }
      >
        <p className="text-sm">
          Payments using <span className="mono">{removing?.entry_value}</span> will no longer be flagged by rule R6. The removal is recorded in the audit log.
        </p>
      </Modal>
    </PageShell>
  );
}
