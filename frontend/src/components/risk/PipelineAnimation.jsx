import clsx from 'clsx';
import { motion, useReducedMotion } from 'framer-motion';
import { Bell, Calculator, Database, Inbox, ListChecks, RotateCcw, Scale } from 'lucide-react';
import { useEffect, useState } from 'react';

export const STAGES = [
  { key: 'ingest', label: 'Receive', icon: Inbox, text: 'The bank sends the payment to FraudShield.' },
  { key: 'save', label: 'Save', icon: Database, text: 'It is saved in MySQL as “pending”.' },
  { key: 'rules', label: 'Check rules', icon: ListChecks, text: 'The stored procedure runs all 9 checks.' },
  { key: 'score', label: 'Score', icon: Calculator, text: 'Warning signs are added up (max 100).' },
  { key: 'decide', label: 'Decide', icon: Scale, text: 'Approve, hold or block.' },
  { key: 'alert', label: 'Alert', icon: Bell, text: 'Analysts and the customer are told.' },
];

/**
 * The six stages lighting up one after another, each with the real time it
 * took for this payment. Without timings it plays as an illustration.
 */
export default function PipelineAnimation({ timings, status, compact = false }) {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? STAGES.length : 0);
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (reduce) return undefined;
    setStep(0);
    const ids = STAGES.map((_, i) => setTimeout(() => setStep(i + 1), 350 * (i + 1)));
    return () => ids.forEach(clearTimeout);
  }, [run, reduce, timings]);

  const doneColor = status === 'BLOCKED' ? 'bg-blocked' : status === 'REVIEW' ? 'bg-review' : 'bg-approved';
  const total = timings ? Object.values(timings).reduce((a, b) => a + Number(b || 0), 0) : null;

  return (
    <div>
      <ol className={clsx('grid gap-3', compact ? 'grid-cols-3 sm:grid-cols-6' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6')}>
        {STAGES.map((s, i) => {
          const lit = step > i;
          const Icon = s.icon;
          return (
            <li key={s.key} className="relative">
              <motion.div
                animate={{ scale: lit && step === i + 1 ? [1, 1.06, 1] : 1 }}
                transition={{ duration: 0.3 }}
                className={clsx(
                  'flex h-full flex-col items-center gap-1.5 rounded-2xl border p-3 text-center transition-colors duration-300',
                  lit ? 'border-primary/40 bg-primary-soft' : 'border-line bg-surface2/50',
                )}
              >
                <span className={clsx('rounded-xl p-2 text-white transition-colors', lit ? (i === 4 ? doneColor : 'bg-primary') : 'bg-line')}>
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <span className="text-xs font-semibold">{s.label}</span>
                {timings && <span className="num text-[11px] text-muted">{Number(timings[s.key] || 0).toFixed(2)} ms</span>}
                {!compact && <span className="hidden text-[11px] leading-snug text-muted sm:block">{s.text}</span>}
              </motion.div>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>{total != null ? `Total inside FraudShield: ${total.toFixed(1)} ms` : 'How every payment is checked'}</span>
        <button onClick={() => setRun((r) => r + 1)} className="inline-flex items-center gap-1 hover:text-ink">
          <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Replay
        </button>
      </div>
    </div>
  );
}
