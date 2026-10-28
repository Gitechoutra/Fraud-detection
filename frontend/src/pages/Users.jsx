import { Pencil, UserPlus, Users as UsersIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { errorMessage } from '../api/client';
import { userApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Modal from '../components/ui/Modal';
import Table from '../components/ui/Table';
import useAuth from '../hooks/useAuth';
import { exactTime, timeAgo, titleCase } from '../utils/format';

const ROLES = {
  ANALYST: 'Watches payments, investigates alerts and cases',
  RISK_MANAGER: 'Also tunes rules, the watchlist and runs the Fraud Lab',
  ADMIN: 'Everything, including managing users',
};
const EMPTY = { username: '', full_name: '', password: '', role: 'ANALYST', is_active: true };

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = () => userApi.list().then(setUsers).catch((err) => toast.error(errorMessage(err)));
  useEffect(() => {
    load();
  }, []);

  const open = (u) => {
    setEditing(u || 'new');
    setForm(u ? { ...EMPTY, ...u, password: '' } : EMPTY);
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (editing === 'new') {
        await userApi.create({ username: form.username, full_name: form.full_name, password: form.password, role: form.role });
        toast.success(`User ${form.username} created`);
      } else {
        const body = { full_name: form.full_name, role: form.role, is_active: form.is_active };
        if (form.password) body.password = form.password;
        await userApi.update(editing.id, body);
        toast.success(`User ${editing.username} updated`);
      }
      setEditing(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    {
      key: 'name',
      label: 'Person',
      render: (u) => (
        <div>
          <p className="font-medium">{u.full_name}</p>
          <p className="mono text-xs text-muted">{u.username}</p>
        </div>
      ),
    },
    { key: 'role', label: 'Role', render: (u) => <Badge tone={u.role === 'ADMIN' ? 'primary' : 'neutral'}>{titleCase(u.role)}</Badge> },
    { key: 'is_active', label: 'Status', render: (u) => <Badge tone={u.is_active ? 'approved' : 'blocked'}>{u.is_active ? 'Active' : 'Disabled'}</Badge> },
    {
      key: 'last_login_at',
      label: 'Last login',
      hideOnMobile: true,
      render: (u) => <span className="text-xs text-muted" title={exactTime(u.last_login_at)}>{u.last_login_at ? timeAgo(u.last_login_at) : 'never'}</span>,
    },
    {
      key: 'edit',
      label: '',
      className: 'text-right',
      render: (u) => (
        <button onClick={() => open(u)} className="rounded-lg p-1.5 text-muted hover:bg-surface2 hover:text-ink" aria-label={`Edit ${u.username}`}>
          <Pencil className="h-4 w-4" />
        </button>
      ),
    },
  ];

  const isSelf = editing && editing !== 'new' && editing.id === me?.id;
  return (
    <PageShell title="Users" subtitle="Who can sign in to FraudShield and what each person is allowed to do." actions={<Button icon={UserPlus} onClick={() => open(null)}>Add user</Button>}>
      <Card bodyClass="p-4">
        <Table columns={columns} rows={users} loading={!users} empty={{ icon: UsersIcon, title: 'No users' }} />
      </Card>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add a user' : `Edit ${editing?.username}`}>
        <form onSubmit={save} className="space-y-3">
          {editing === 'new' && (
            <div>
              <label className="label" htmlFor="u-username">Username</label>
              <input id="u-username" className="input" required pattern="[a-zA-Z0-9_.\-]{3,64}" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="u-name">Full name</label>
            <input id="u-name" className="input" required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor="u-pass">{editing === 'new' ? 'Password (8+ characters)' : 'New password (leave empty to keep)'}</label>
            <input id="u-pass" className="input" type="password" minLength={8} required={editing === 'new'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <fieldset>
            <legend className="label">Role</legend>
            <div className="space-y-1.5">
              {Object.entries(ROLES).map(([k, v]) => (
                <label key={k} className="flex cursor-pointer items-start gap-2 rounded-xl border border-line p-2.5 has-[:checked]:border-primary has-[:checked]:bg-primary-soft">
                  <input type="radio" name="role" className="mt-1 accent-primary" checked={form.role === k} disabled={isSelf} onChange={() => setForm({ ...form, role: k })} />
                  <span>
                    <span className="block text-sm font-medium">{titleCase(k)}</span>
                    <span className="block text-xs text-muted">{v}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {editing !== 'new' && !isSelf && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-primary" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
              Can sign in
            </label>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save</Button>
          </div>
        </form>
      </Modal>
    </PageShell>
  );
}
