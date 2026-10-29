import { useState } from 'react';

// Approximate positions (longitude, latitude) of the demo cities.
const COORDS = {
  Delhi: [77.21, 28.61],
  Jaipur: [75.79, 26.91],
  Lucknow: [80.95, 26.85],
  Ahmedabad: [72.57, 23.02],
  Kolkata: [88.36, 22.57],
  Mumbai: [72.88, 19.08],
  Pune: [73.86, 18.52],
  Hyderabad: [78.49, 17.39],
  Visakhapatnam: [83.22, 17.69],
  Bengaluru: [77.59, 12.97],
  Chennai: [80.27, 13.08],
  Kochi: [76.27, 9.93],
};
// Cities that sit close to a neighbour get their label below / to the side.
const LABEL_POS = { Pune: 'below', Chennai: 'right', Visakhapatnam: 'right', Kochi: 'below', Jaipur: 'left' };
const LON = [68, 92];
const LAT = [7, 31];
const W = 320;
const H = 340;
function labelProps(pos, r) {
  if (pos === 'below') return { y: r + 12, textAnchor: 'middle' };
  if (pos === 'right') return { x: r + 4, y: 4, textAnchor: 'start' };
  if (pos === 'left') return { x: -r - 4, y: 4, textAnchor: 'end' };
  return { y: -r - 5, textAnchor: 'middle' };
}
const x = (lon) => ((lon - LON[0]) / (LON[1] - LON[0])) * W;
const y = (lat) => H - ((lat - LAT[0]) / (LAT[1] - LAT[0])) * H;

/**
 * Where payments happen: one dot per city at its rough map position, sized by
 * number of payments; the red ring shows how many were held or blocked.
 * A ranked list beside it gives exact numbers (and works without the picture).
 */
export default function CityMap({ data }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...data.map((d) => d.total));
  const rows = data.filter((d) => COORDS[d.city]);
  return (
    <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <svg viewBox={`-20 -10 ${W + 40} ${H + 20}`} className="mx-auto w-full max-w-xs" role="img" aria-label="Map of payments by city">
        <rect x="-20" y="-10" width={W + 40} height={H + 20} rx="16" fill="rgb(var(--surface-2))" />
        {rows.map((d) => {
          const [lon, lat] = COORDS[d.city];
          const r = 6 + 18 * Math.sqrt(d.total / max);
          const flaggedR = d.total ? r * Math.sqrt(d.flagged / d.total) : 0;
          const active = hover === d.city;
          return (
            <g
              key={d.city}
              transform={`translate(${x(lon)} ${y(lat)})`}
              onMouseEnter={() => setHover(d.city)}
              onMouseLeave={() => setHover(null)}
              className="cursor-default"
            >
              <circle r={r + 6} fill="transparent" />
              <circle r={r} fill="#6366F1" fillOpacity={active ? 0.55 : 0.32} stroke="rgb(var(--surface))" strokeWidth="2" />
              {flaggedR > 0 && <circle r={Math.max(2.5, flaggedR)} fill="#EF4444" stroke="rgb(var(--surface))" strokeWidth="2" />}
              <text
                {...labelProps(LABEL_POS[d.city], r)}
                className="fill-ink"
                fontSize="11"
                fontWeight={active ? 600 : 400}
              >
                {d.city}
              </text>
              {active && (
                <text y={r + 14} textAnchor="middle" className="fill-muted" fontSize="10">
                  {d.total.toLocaleString('en-IN')} · {d.flagged} flagged
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <ol className="space-y-1.5 text-sm">
        {data.slice(0, 8).map((d, i) => (
          <li
            key={d.city}
            onMouseEnter={() => setHover(d.city)}
            onMouseLeave={() => setHover(null)}
            className={`flex items-center justify-between gap-2 rounded-lg px-2 py-1 ${hover === d.city ? 'bg-surface2' : ''}`}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="num w-4 text-xs text-muted">{i + 1}</span>
              <span className="truncate">{d.city}</span>
            </span>
            <span className="num shrink-0 text-xs text-muted">
              {d.total.toLocaleString('en-IN')} <span className="text-review" title="alerts (held or blocked)">· {d.flagged}</span>{' '}
              <span className="text-blocked" title="confirmed fraud">· {d.confirmed_fraud || 0}</span>
            </span>
          </li>
        ))}
        <li className="flex gap-3 px-2 pt-1 text-[11px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-primary" /> payments
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blocked" /> held or blocked
          </span>
          <span className="num">count · alerts · confirmed fraud</span>
        </li>
      </ol>
    </div>
  );
}
