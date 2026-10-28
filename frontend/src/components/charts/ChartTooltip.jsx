/** Recharts tooltip in the app's surface colours; values in text colour,
 *  a small swatch carries the series identity. */
export default function ChartTooltip({ active, payload, label, format = (v) => Number(v).toLocaleString('en-IN') }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-soft">
      {label != null && <p className="mb-1 font-medium text-ink">{label}</p>}
      {payload.map((p) => (
        <div key={p.dataKey || p.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted">
            <span className="h-2 w-2 rounded-sm" style={{ background: p.color || p.payload?.fill }} />
            {p.name}
          </span>
          <span className="num text-ink">{format(p.value, p)}</span>
        </div>
      ))}
    </div>
  );
}
