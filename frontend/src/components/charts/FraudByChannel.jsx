import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from './ChartTooltip';

const NAMES = { CARD: 'Card', UPI: 'UPI', NETBANKING: 'Net banking', ATM: 'ATM' };

/** Per channel: share of payments held or blocked (alert rate) and share confirmed as fraud by an analyst (fraud rate). */
export default function FraudByChannel({ data }) {
  const rows = data.map((d) => ({
    channel: NAMES[d.channel] || d.channel,
    rate: d.total ? (100 * d.flagged) / d.total : 0,
    fraudRate: d.total ? (100 * (d.confirmed_fraud || 0)) / d.total : 0,
    flagged: d.flagged,
    fraud: d.confirmed_fraud || 0,
    total: d.total,
  }));
  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 48, left: 8, bottom: 0 }}>
        <CartesianGrid horizontal={false} strokeDasharray="3 3" />
        <XAxis type="number" tickLine={false} axisLine={false} unit="%" />
        <YAxis type="category" dataKey="channel" tickLine={false} axisLine={false} width={84} />
        <Tooltip
          cursor={{ fill: 'rgb(var(--surface-2))' }}
          content={
            <ChartTooltip
              format={(v, p) =>
                `${v.toFixed(2)}% (${p.dataKey === 'rate' ? p.payload.flagged : p.payload.fraud} of ${p.payload.total.toLocaleString('en-IN')})`
              }
            />
          }
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="rate" name="Alert rate (held or blocked)" fill="#6366F1" radius={[0, 4, 4, 0]} barSize={12}>
          <LabelList dataKey="rate" position="right" formatter={(v) => `${v.toFixed(1)}%`} className="fill-ink text-[11px]" />
        </Bar>
        <Bar dataKey="fraudRate" name="Fraud rate (confirmed)" fill="#EF4444" radius={[0, 4, 4, 0]} barSize={12}>
          <LabelList dataKey="fraudRate" position="right" formatter={(v) => `${v.toFixed(1)}%`} className="fill-ink text-[11px]" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
