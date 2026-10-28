import CountUp from 'react-countup';

const reduceMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Counts up to `value`; `format` turns the running number into text. */
export default function AnimatedNumber({
  value,
  format = (v) => Math.round(v).toLocaleString('en-IN'),
  duration = 1.1,
}) {
  if (reduceMotion()) return <span className="num">{format(Number(value || 0))}</span>;
  return (
    <CountUp end={Number(value || 0)} duration={duration} preserveValue formattingFn={format}>
      {({ countUpRef }) => <span className="num" ref={countUpRef} />}
    </CountUp>
  );
}
