import { ArrowLeft, ArrowLeftRight } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import AttackerConsole from '../components/demo/AttackerConsole';
import CustomerApp from '../components/demo/CustomerApp';
import ThemeToggle from '../components/layout/ThemeToggle';
import { inr } from '../utils/format';

/**
 * Split screen: the fraudster's console and the victim's phone, side by side
 * (stacked on small screens). Each side is its own logged-in client talking
 * to the real API — the decisions and alerts come only from the backend.
 */
export default function DemoSplit() {
  const [last, setLast] = useState(null);
  return (
    <div className="min-h-screen px-3 py-3 sm:px-5">
      <header className="mx-auto mb-3 flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <Link to="/" className="flex items-center gap-1 text-sm text-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Home
        </Link>
        <p className="flex items-center gap-2 text-sm font-semibold">
          <ArrowLeftRight className="h-4 w-4 text-primary" /> Live demo: fraudster vs. customer
        </p>
        <div className="flex items-center gap-3 text-sm">
          <Link to="/login" className="text-muted hover:text-ink">
            Staff dashboard
          </Link>
          <ThemeToggle />
        </div>
      </header>
      {last && (
        <p className="mx-auto mb-3 max-w-7xl rounded-xl border border-line bg-surface px-3 py-2 text-xs">
          Last attack: <strong>{last.scenario}</strong> on {last.victim.name} — bank decision <strong>{last.bank_decision}</strong>
          {last.steps.filter((s) => s.status).length > 0 &&
            ` (${last.steps.filter((s) => s.status).map((s) => `${inr(s.amount)} ${s.status}`).join(', ')})`}
          . Log in on the phone as <strong>{last.victim.username}</strong> to see the alert.
        </p>
      )}
      <div className="mx-auto grid max-w-7xl items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section aria-label="Fraudster console" className="min-w-0">
          <AttackerConsole compact onActivity={setLast} />
        </section>
        <section aria-label="Victim's phone" className="min-w-0">
          <p className="mb-2 text-center text-xs text-muted">Victim&apos;s phone (customer app)</p>
          <CustomerApp compact />
        </section>
      </div>
    </div>
  );
}