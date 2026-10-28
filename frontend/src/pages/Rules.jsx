import clsx from 'clsx';
import { History, Lock, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { errorMessage } from '../api/client';
import { ruleApi } from '../api/endpoints';
import PageShell from '../components/layout/PageShell';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Modal from '../components/ui/Modal';
import Skeleton from '../components/ui/Skeleton';
import useAuth from '../hooks/useAuth';
import { timeAgo } from '../utils/format';
import { RULES, rulePreview } from '../utils/ruleInfo';

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        'relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50',
        checked ? 'bg-approved' : 'bg-line',
      )}
    >
      <span className={clsx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-0.5')} />
    </button>
  );
}

function RuleCard({ rule, canEdit, onSaved }) {
  const [draft, setDraft] = useState(() => ({ params: rule.params, weight: rule.weight, is_active: rule.is_active }));
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const info = RULES[rule.rule_code];
  const Icon = info.icon;
  const dirty =
    draft.weight !== rule.weight || draft.is_active !== rule.is_active || draft.params.some((p, i) => p !== rule.params[i]);

  useEffect(() => setDraft({ params: rule.params, weight: rule.weight, is_active: rule.is_active }), [rule]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { weight: draft.weight, is_active: draft.is_active };
      rule.param_labels.forEach((_, i) => (body[`param_${i + 1}`] = draft.params[i]));
      await ruleApi.update(rule.rule_code, body);
      toast.success(`Rule ${rule.rule_code} updated — applies to the next payment`);
      setConfirm(false);
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const precision = rule.stats?.precision_v;
  return (
    <div className={clsx('card flex flex-col p-5 transition', !draft.is_active && 'opacity-70')}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-primary-soft p-2 text-primary">
            <Icon className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="text-xs font-medium text-muted">{rule.rule_code}</p>
            <h3 className="font-semibold leading-tight">{info.name}</h3>
          </div>
        </div>
        <Toggle
          checked={draft.is_active}
          disabled={!canEdit}
          onChange={(v) => setDraft({ ...draft, is_active: v })}
          label={`Turn rule ${rule.rule_code} ${draft.is_active ? 'off' : 'on'}`}
        />
      </div>
      <p className="mt-3 text-sm text-muted">{info.what}</p>

      <p className="mt-3 rounded-xl bg-surface2/70 px-3 py-2 text-sm">{rulePreview(rule.rule_code, draft.params)}</p>

      <div className="mt-4 grid grid-cols-2 gap-3">
        {rule.param_labels.map((label, i) => (
          <label key={label} className="block">
            <span className="label normal-case tracking-normal">{label}</span>
            <input
              type="number"
              min="0"
              step="any"
              className="input num py-2"
              value={draft.params[i] ?? ''}
              disabled={!canEdit}
              onChange={(e) => {
                const params = [...draft.params];
                params[i] = e.target.value === '' ? null : Number(e.target.value);
                setDraft({ ...draft, params });
              }}
            />
          </label>
        ))}
      </div>

      <label className="mt-4 block">
        <span className="label flex justify-between normal-case tracking-normal">
          Risk points when it fires <span className="num text-ink">{draft.weight}</span>
        </span>
        <input
          type="range"
          min="0"
          max="100"
          value={draft.weight}
          disabled={!canEdit}
          onChange={(e) => setDraft({ ...draft, weight: Number(e.target.value) })}
          className="w-full accent-primary"
          aria-label={`Weight of rule ${rule.rule_code}`}
        />
      </label>

      <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-xs text-muted">
        <span>
          Fired {rule.stats?.hits ?? 0}× · {precision == null ? 'no closed cases' : `right ${Math.round(precision * 100)}% of the time`}
        </span>
        {canEdit && (
          <Button size="sm" icon={Save} disabled={!dirty} onClick={() => setConfirm(true)}>
            Save
          </Button>
        )}
      </div>

      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Save changes to ${rule.rule_code}?`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={save}>
              Save change
            </Button>
          </>
        }
      >
        <p className="text-sm">{rulePreview(rule.rule_code, draft.params)}</p>
        <p className="mt-2 text-sm text-muted">
          Adds <strong className="text-ink">{draft.weight}</strong> risk points when it fires. Rule is{' '}
          <strong className="text-ink">{draft.is_active ? 'on' : 'off'}</strong>. The database uses the new values from the very next payment, and
          the change is recorded in the audit log.
        </p>
      </Modal>
    </div>
  );
}

function BandsCard({ bands, canEdit, onSaved }) {
  const [draft, setDraft] = useState(bands);
  const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(bands), [bands]);
  const save = async () => {
    setBusy(true);
    try {
      await ruleApi.bands(draft);
      toast.success('Decision bands updated');
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const r = draft.review_threshold;
  const b = draft.block_threshold;
  return (
    <Card title="Decision bands" subtitle="The risk score (0–100) is the sum of the points of every rule that fired.">
      <div className="relative h-3 overflow-hidden rounded-full" aria-hidden>
        <div className="absolute inset-y-0 left-0 bg-approved" style={{ width: `${r}%` }} />
        <div className="absolute inset-y-0 bg-review" style={{ left: `${r}%`, width: `${b - r}%` }} />
        <div className="absolute inset-y-0 right-0 bg-blocked" style={{ left: `${b}%` }} />
      </div>
      <div className="mt-2 grid grid-cols-3 text-xs">
        <span>0–{r - 1}: <strong>Approve</strong></span>
        <span className="text-center">{r}–{b - 1}: <strong>Hold for review</strong></span>
        <span className="text-right">{b}–100: <strong>Block</strong></span>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {[
          ['review_threshold', 'Hold from score', 1, 99],
          ['block_threshold', 'Block from score', 2, 100],
        ].map(([key, label, min, max]) => (
          <label key={key}>
            <span className="label flex justify-between normal-case tracking-normal">
              {label} <span className="num text-ink">{draft[key]}</span>
            </span>
            <input
              type="range"
              min={min}
              max={max}
              value={draft[key]}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, [key]: Number(e.target.value) })}
              className="w-full accent-primary"
            />
          </label>
        ))}
      </div>
      {canEdit && (
        <div className="mt-3 flex justify-end">
          <Button size="sm" icon={Save} loading={busy} disabled={r >= b || (r === bands.review_threshold && b === bands.block_threshold)} onClick={save}>
            Save bands
          </Button>
        </div>
      )}
    </Card>
  );
}

export default function Rules() {
  const { hasRole } = useAuth();
  const canEdit = hasRole('RISK_MANAGER');
  const [data, setData] = useState(null);
  const load = () => ruleApi.list().then(setData).catch((err) => toast.error(errorMessage(err)));
  useEffect(() => {
    load();
  }, []);

  return (
    <PageShell
      title="Rules console"
      subtitle="The nine checks that run inside MySQL for every payment. Change a limit here and the very next payment uses it."
      actions={
        !canEdit && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-xs text-muted">
            <Lock className="h-3.5 w-3.5" aria-hidden /> View only — risk managers can edit
          </span>
        )
      }
    >
      {!data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : (
        <>
          <BandsCard bands={data.bands} canEdit={canEdit} onSaved={load} />
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.rules.map((r) => (
              <RuleCard key={r.rule_code} rule={r} canEdit={canEdit} onSaved={load} />
            ))}
          </div>
          <Card className="mt-4" title="Change history" subtitle="Recorded automatically by a database trigger." action={<History className="h-4 w-4 text-muted" />}>
            {data.history.length === 0 ? (
              <p className="text-sm text-muted">No changes yet.</p>
            ) : (
              <ul className="divide-y divide-line text-sm">
                {data.history.map((h) => (
                  <li key={h.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
                    <span>
                      <strong>{h.actor}</strong> {h.action === 'BANDS_UPDATED' ? 'changed the decision bands' : `changed rule ${h.entity_id}`}
                      <span className="ml-2 text-xs text-muted">
                        {h.old_value && h.new_value
                          ? Object.keys(h.new_value)
                              .filter((k) => String(h.old_value[k]) !== String(h.new_value[k]))
                              .map((k) => `${k.replace('_', ' ')}: ${h.old_value[k]} → ${h.new_value[k]}`)
                              .join(', ')
                          : ''}
                      </span>
                    </span>
                    <span className="text-xs text-muted">{timeAgo(h.logged_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </PageShell>
  );
}
