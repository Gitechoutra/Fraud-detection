import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { RULES } from '../../utils/ruleInfo';
import ChartTooltip from './ChartTooltip';

/**
 * One bar per rule. `valueKey` is "hits" (count) or "precision" (0..1,
 * shown as %). Single series, so no legend: the card title names it.
 */
export default function RuleHitsChart({ data, valueKey = 'hits' }) {
  const isPct = valueKey === 'precision';
  const rows = data.map((d) => ({
    code: d.rule_code,
    name: RULES[d.rule_code]?.name || d.simple_name,
    value: isPct ? (d.precision_v == null ? null : Number(d.precision_v) * 100) : Number(d.hits || 0),
    empty: isPct && d.precision_v == null,
  }));
  const fmt = (v) => (v == null ? 'no data' : isPct ? `${Math.round(v)}%` : Number(v).toLocaleString('en-IN'));
  // Bars with no data still get a label at the baseline, so "no closed cases" never reads as 0%.
  rows.forEach((r) => {
    r.label = fmt(r.value);
    if (r.value == null) r.value = 0;
  });
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 18, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="code" tickLine={false} axisLine={false} />
        <YAxis tickLine={false} axisLine={false} width={isPct ? 52 : 44} domain={isPct ? [0, 100] : [0, 'auto']} unit={isPct ? '%' : ''} />
        <Tooltip
          cursor={{ fill: 'rgb(var(--surface-2))' }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <ChartTooltip
                active
                label={`${payload[0].payload.code} · ${payload[0].payload.name}`}
                payload={payload}
                format={(v, p) => (p.payload.empty ? 'no closed cases yet' : fmt(v))}
              />
            ) : null
          }
        />
        <Bar dataKey="value" name={isPct ? 'Precision' : 'Times fired'} fill="#6366F1" radius={[4, 4, 0, 0]} maxBarSize={36}>
          <LabelList dataKey="label" position="top" className="fill-muted text-[10px]" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
