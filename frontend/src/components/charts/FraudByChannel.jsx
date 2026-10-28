import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from './ChartTooltip';

const NAMES = { CARD: 'Card', UPI: 'UPI', NETBANKING: 'Net banking', ATM: 'ATM' };

/** Share of each channel's payments that were held or blocked (one measure, one axis). */
export default function FraudByChannel({ data }) {
  const rows = data.map((d) => ({
    channel: NAMES[d.channel] || d.channel,
    rate: d.total ? (100 * d.flagged) / d.total : 0,
    flagged: d.flagged,
    total: d.total,
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 48, left: 8, bottom: 0 }}>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" />
        <XAxis type="number" tickLine={false} axisLine={false} unit="%" />
        <YAxis type="category" dataKey="channel" tickLine={false} axisLine={false} width={84} />
        <Tooltip
          cursor={{ fill: 'rgb(var(--surface-2))' }}
          content={
            <ChartTooltip format={(v, p) => `${v.toFixed(2)}% (${p.payload.flagged} of ${p.payload.total.toLocaleString('en-IN')})`} />
          }
        />
        <Bar dataKey="rate" name="Held or blocked" fill="#6366F1" radius={[0, 4, 4, 0]} barSize={18}>
          <LabelList dataKey="rate" position="right" formatter={(v) => `${v.toFixed(1)}%`} className="fill-ink text-[11px]" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
