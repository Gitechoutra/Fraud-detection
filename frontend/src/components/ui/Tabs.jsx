import clsx from 'clsx';
import { motion } from 'framer-motion';

export default function Tabs({ tabs, value, onChange, id = 'tabs' }) {
  return (
    <div role="tablist" className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface2 p-1">
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={clsx(
              'relative rounded-lg px-3 py-1.5 text-xs font-medium transition',
              active ? 'text-ink' : 'text-muted hover:text-ink',
            )}
          >
            {active && (
              <motion.span
                layoutId={`${id}-pill`}
                className="absolute inset-0 rounded-lg bg-surface shadow-sm"
                transition={{ duration: 0.2 }}
              />
            )}
            <span className="relative flex items-center gap-1.5">
              {t.label}
              {t.count != null && <span className="num rounded-md bg-bg/60 px-1.5 text-[10px]">{t.count}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
