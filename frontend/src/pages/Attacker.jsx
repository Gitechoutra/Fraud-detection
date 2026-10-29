import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import AttackerConsole from '../components/demo/AttackerConsole';

/** Fraudster simulation console (/attacker) — clearly labelled, demo only. */
export default function Attacker() {
  return (
    <div className="min-h-screen bg-[#05070c] px-3 py-4 text-slate-100 sm:px-6">
      <div className="mx-auto mb-3 flex max-w-5xl items-center justify-between text-sm">
        <Link to="/" className="flex items-center gap-1 text-slate-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" /> Home
        </Link>
        <span className="font-semibold">Fraudster demo</span>
        <Link to="/demo" className="text-slate-400 hover:text-white">
          Split screen
        </Link>
      </div>
      <div className="mx-auto max-w-5xl">
        <AttackerConsole />
      </div>
    </div>
  );
}