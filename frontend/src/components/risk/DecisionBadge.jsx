import clsx from 'clsx';
import { CheckCircle2, Loader2, PauseCircle, ShieldX } from 'lucide-react';
import { DECISIONS } from '../../utils/ruleInfo';
import Tooltip from '../ui/Tooltip';

const STYLE = {
  APPROVED: { icon: CheckCircle2, cls: 'bg-approved-soft text-approved border-approved/30' },
  REVIEW: { icon: PauseCircle, cls: 'bg-review-soft text-review border-review/30' },
  BLOCKED: { icon: ShieldX, cls: 'bg-blocked-soft text-blocked border-blocked/30' },
  PENDING: { icon: Loader2, cls: 'bg-primary-soft text-primary border-primary/30' },
};

/** Decision shown with colour + icon + words (never colour alone). */
export default function DecisionBadge({ status, size = 'md' }) {
  const s = STYLE[status] || STYLE.PENDING;
  const Icon = s.icon;
  const info = DECISIONS[status] || DECISIONS.PENDING;
  return (
    <Tooltip text={info.simple}>
      <span
        className={clsx(
          'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-medium',
          s.cls,
          size === 'lg' ? 'px-4 py-1.5 text-base' : 'px-2.5 py-0.5 text-xs',
        )}
      >
        <Icon className={clsx(size === 'lg' ? 'h-5 w-5' : 'h-3.5 w-3.5', status === 'PENDING' && 'animate-spin')} aria-hidden />
        {info.label}
      </span>
    </Tooltip>
  );
}
