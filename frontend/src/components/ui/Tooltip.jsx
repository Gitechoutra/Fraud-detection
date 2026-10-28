/** Lightweight hover/focus tooltip. Hidden with display:none (not just
 *  transparent) so it never widens the page near the screen edge. */
export default function Tooltip({ text, children, className = '' }) {
  if (!text) return children;
  return (
    <span className={`group relative inline-flex ${className}`}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden w-max max-w-[min(20rem,80vw)] -translate-x-1/2 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-normal text-ink shadow-soft group-hover:block group-focus-within:block"
      >
        {text}
      </span>
    </span>
  );
}
