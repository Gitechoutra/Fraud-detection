import { motion, useReducedMotion } from 'framer-motion';

const COLORS = { APPROVED: '#10B981', REVIEW: '#F59E0B', BLOCKED: '#EF4444' };

export function bandOf(score, bands = { review: 40, block: 70 }) {
  if (score >= bands.block) return 'BLOCKED';
  if (score >= bands.review) return 'REVIEW';
  return 'APPROVED';
}

/**
 * Semicircle gauge that sweeps from 0 to `score` (0-100); its colour follows
 * the decision band. size="sm" is the table version.
 */
export default function RiskGauge({ score = 0, bands, size = 'lg', label = true }) {
  const reduce = useReducedMotion();
  const band = bandOf(score, bands);
  const color = COLORS[band];
  const w = size === 'sm' ? 56 : 220;
  const stroke = size === 'sm' ? 6 : 16;
  const r = (w - stroke) / 2;
  const h = r + stroke;
  const arc = `M ${stroke / 2} ${h - stroke / 2} A ${r} ${r} 0 0 1 ${w - stroke / 2} ${h - stroke / 2}`;
  const value = Math.max(0, Math.min(100, Number(score) || 0)) / 100;

  return (
    <div
      className="relative inline-flex flex-col items-center"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-label={`Risk score ${score} out of 100`}
    >
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <path d={arc} fill="none" stroke="rgb(var(--line))" strokeWidth={stroke} strokeLinecap="round" />
        <motion.path
          d={arc}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          initial={{ pathLength: reduce ? value : 0 }}
          animate={{ pathLength: value }}
          transition={{ duration: reduce ? 0 : 1.1, ease: 'easeOut' }}
        />
      </svg>
      {size === 'sm' ? (
        <span className="num -mt-3 text-xs font-semibold">{score}</span>
      ) : (
        label && (
          <div className="-mt-14 flex flex-col items-center">
            <span className="num text-4xl font-semibold" style={{ color }}>
              {score}
            </span>
            <span className="text-xs text-muted">risk out of 100</span>
          </div>
        )
      )}
    </div>
  );
}
