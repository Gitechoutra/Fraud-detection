import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from './ChartTooltip';

/** Payments over time, stacked by decision (2px surface gap between segments). */
export default function VolumeChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barCategoryGap="18%">
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={12} />
        <YAxis tickLine={false} axisLine={false} allowDecimals={false} width={44} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgb(var(--surface-2))' }} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="approved" name="Approved" stackId="a" fill="#10B981" stroke="rgb(var(--surface))" strokeWidth={1} />
        <Bar dataKey="review" name="Held for review" stackId="a" fill="#F59E0B" stroke="rgb(var(--surface))" strokeWidth={1} />
        <Bar
          dataKey="blocked"
          name="Blocked"
          stackId="a"
          fill="#EF4444"
          stroke="rgb(var(--surface))"
          strokeWidth={1}
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
