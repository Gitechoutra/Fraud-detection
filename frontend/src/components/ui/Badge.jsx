import clsx from 'clsx';

const TONES = {
  neutral: 'bg-surface2 text-muted border-line',
  primary: 'bg-primary-soft text-primary border-primary/20',
  approved: 'bg-approved-soft text-approved border-approved/25',
  review: 'bg-review-soft text-review border-review/25',
  blocked: 'bg-blocked-soft text-blocked border-blocked/25',
};

export default function Badge({ tone = 'neutral', icon: Icon, className, children }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium',
        TONES[tone],
        className,
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
      {children}
    </span>
  );
}
