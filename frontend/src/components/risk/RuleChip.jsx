import { RULES } from '../../utils/ruleInfo';
import Tooltip from '../ui/Tooltip';

/** "R3" chip with its icon; hover shows the plain-English name. */
export default function RuleChip({ code }) {
  const info = RULES[code];
  if (!info) return null;
  const Icon = info.icon;
  return (
    <Tooltip text={`${info.name} — ${info.what}`}>
      <span className="inline-flex items-center gap-1 rounded-md border border-line bg-surface2 px-1.5 py-0.5 text-[11px] font-medium text-ink">
        <Icon className="h-3 w-3 text-primary" aria-hidden />
        {code}
      </span>
    </Tooltip>
  );
}
