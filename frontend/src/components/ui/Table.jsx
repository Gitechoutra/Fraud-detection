import clsx from 'clsx';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import Skeleton from './Skeleton';
import EmptyState from './EmptyState';

/**
 * columns: [{ key, label, render?(row), className?, hideOnMobile? }]
 * On small screens rows become stacked cards, so nothing scrolls sideways.
 */
export default function Table({ columns, rows, loading, onRowClick, empty, rowKey = 'id', rowClass }) {
  if (loading && !rows?.length) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-11" />
        ))}
      </div>
    );
  }
  if (!rows?.length) return <EmptyState {...empty} />;
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              {columns.map((c) => (
                <th key={c.key} className={clsx('px-3 py-2.5 font-medium', c.className)}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row[rowKey]}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (e) => e.key === 'Enter' && onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                className={clsx(
                  'border-b border-line/60 last:border-0',
                  onRowClick && 'cursor-pointer hover:bg-surface2/70',
                  rowClass?.(row),
                )}
              >
                {columns.map((c) => (
                  <td key={c.key} className={clsx('px-3 py-2.5 align-middle', c.className)}>
                    {c.render ? c.render(row) : row[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-2 md:hidden">
        {rows.map((row) => (
          <li
            key={row[rowKey]}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={clsx('rounded-xl border border-line bg-surface2/50 p-3', onRowClick && 'cursor-pointer')}
          >
            {columns
              .filter((c) => !c.hideOnMobile)
              .map((c) => (
                <div key={c.key} className="flex items-center justify-between gap-3 py-0.5 text-sm">
                  <span className="text-xs text-muted">{c.label}</span>
                  <span className="min-w-0 text-right">{c.render ? c.render(row) : row[c.key]}</span>
                </div>
              ))}
          </li>
        ))}
      </ul>
    </>
  );
}

export function Pager({ page, pages, onPage }) {
  if (!pages || pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-end gap-2 text-sm text-muted">
      <button
        className="rounded-lg border border-line p-1.5 hover:text-ink disabled:opacity-40"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <span className="num">
        {page} / {pages}
      </span>
      <button
        className="rounded-lg border border-line p-1.5 hover:text-ink disabled:opacity-40"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
