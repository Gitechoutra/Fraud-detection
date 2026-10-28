import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const inrFull = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const inrWhole = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});
const plain = new Intl.NumberFormat('en-IN');

/** ₹1,25,000.00 */
export const inr = (v) => inrFull.format(Number(v || 0));
/** ₹1,25,000 */
export const inrRound = (v) => inrWhole.format(Number(v || 0));
/** ₹1.2 L / ₹3.4 Cr — for tight KPI tiles */
export function inrShort(v) {
  const n = Number(v || 0);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return inrWhole.format(n);
}
export const num = (v) => plain.format(Number(v || 0));
export const pct = (v, digits = 1) => `${(Number(v || 0) * 100).toFixed(digits)}%`;
export const ms = (v) => (v == null ? '—' : `${Number(v).toFixed(Number(v) < 10 ? 1 : 0)} ms`);

/** "2 minutes ago" */
export const timeAgo = (t) => (t ? dayjs(t).fromNow() : '—');
/** "28 Oct 2026, 02:14:09 PM" — shown on hover */
export const exactTime = (t) => (t ? dayjs(t).format('DD MMM YYYY, hh:mm:ss A') : '');
export const shortTime = (t) => (t ? dayjs(t).format('hh:mm:ss A') : '');
export const shortDate = (t) => (t ? dayjs(t).format('DD MMM, hh:mm A') : '');

export const titleCase = (s) =>
  (s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
