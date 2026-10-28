import clsx from 'clsx';

export default function Card({ title, subtitle, action, className, bodyClass, children }) {
  return (
    <section className={clsx('card', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-5">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={bodyClass ?? 'p-5'}>{children}</div>
    </section>
  );
}
