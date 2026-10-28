import clsx from 'clsx';
import { motion } from 'framer-motion';
import { RULES } from '../../utils/ruleInfo';

/**
 * Every rule, in plain English. Rules that fired are bright cards with the
 * exact sentence the database wrote; rules that didn't fire are greyed out
 * so the reader also sees what was checked and found fine.
 */
export default function WhyBlockedPanel({ rules }) {
  const fired = rules.filter((r) => r.fired);
  const quiet = rules.filter((r) => !r.fired);
  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-3 text-sm font-semibold">
          {fired.length ? `${fired.length} warning sign${fired.length > 1 ? 's' : ''} found` : 'No warning signs found'}
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {fired.map((r, i) => {
            const Icon = RULES[r.rule_code]?.icon;
            return (
              <motion.div
                key={r.rule_code}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 * i }}
                className="rounded-2xl border border-blocked/30 bg-blocked-soft p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {Icon && <Icon className="h-4 w-4 text-blocked" aria-hidden />}
                    <p className="text-sm font-semibold">{r.simple_name}</p>
                  </div>
                  <span className="num rounded-md bg-surface px-1.5 py-0.5 text-xs font-semibold">+{r.weight_applied}</span>
                </div>
                <p className="mt-2 text-sm">{r.sentence}</p>
                <p className="mt-1 text-xs text-muted">{RULES[r.rule_code]?.why}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Also checked — all fine</h3>
        <div className="flex flex-wrap gap-2">
          {quiet.map((r) => {
            const Icon = RULES[r.rule_code]?.icon;
            return (
              <span
                key={r.rule_code}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface2/60 px-2.5 py-1.5 text-xs text-muted',
                  !r.is_active && 'line-through',
                )}
                title={r.is_active ? r.simple_explanation : 'This rule is switched off'}
              >
                {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
                {r.simple_name}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
