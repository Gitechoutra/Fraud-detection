import { ScrollText, Search } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { errorMessage } from '../api/client';
import { auditApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import Badge from '../components/ui/Badge';
import Card from '../components/ui/Card';
import Table, { Pager } from '../components/ui/Table';
import { exactTime, timeAgo, titleCase } from '../utils/format';

const ENTITIES = { '': 'Everything', fraud_rules: 'Rules', watchlist: 'Watchlist', cases: 'Cases', users: 'Users', system_settings: 'Decision bands' };

function changes(row) {
  const { old_value: o, new_value: n } = row;
  if (o && n) {
    const diff = Object.keys(n).filter((k) => String(o[k]) !== String(n[k]));
    return diff.map((k) => `${k.replace(/_/g, ' ')}: ${o[k] ?? '—'} → ${n[k] ?? '—'}`).join(', ');
  }
  const v = n || o;
  return v ? Object.entries(v).map(([k, val]) => `${k.replace(/_/g, ' ')}: ${val}`).join(', ') : '';
}

export default function AuditLog() {
  const [res, setRes] = useState(null);
  const [entity, setEntity] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const load = useCallback(
    () =>
      auditApi
        .list({ entity: entity || undefined, search: search || undefined, page })
        .then(setRes)
        .catch((err) => toast.error(errorMessage(err))),
    [entity, search, page],
  );
  useEffect(() => {
    load();
  }, [load]);

  const columns = [
    { key: 'logged_at', label: 'When', render: (r) => <span className="text-xs text-muted" title={exactTime(r.logged_at)}>{timeAgo(r.logged_at)}</span> },
    { key: 'actor', label: 'Who', render: (r) => <span className="font-medium">{r.actor}</span> },
    { key: 'action', label: 'What', render: (r) => <Badge tone={r.action.includes('REMOVED') ? 'blocked' : 'primary'}>{titleCase(r.action)}</Badge> },
    { key: 'entity', label: 'On', render: (r) => <span className="text-sm">{ENTITIES[r.entity] || r.entity} {r.entity_id && <span className="mono text-xs text-muted">#{r.entity_id}</span>}</span> },
    { key: 'details', label: 'Details', hideOnMobile: true, render: (r) => <span className="text-xs text-muted">{changes(r)}</span> },
  ];

  return (
    <PageShell
      title="Audit log"
      subtitle="Every change to rules, the watchlist, cases and users — who did it and when. Rule, watchlist and case changes are recorded by database triggers, so nothing slips through."
    >
      <Card bodyClass="p-4">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row">
          <select className="input sm:w-56" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }} aria-label="Filter by area">
            {Object.entries(ENTITIES).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input className="input pl-9" placeholder="Search person, action or id" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} aria-label="Search audit log" />
          </div>
        </div>
        <Table columns={columns} rows={res?.items} loading={!res} empty={{ icon: ScrollText, title: 'No activity yet', text: 'Changes appear here as soon as someone makes them.' }} />
        <Pager page={res?.page} pages={res?.pages} onPage={setPage} />
      </Card>
    </PageShell>
  );
}
