import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import CustomerApp from '../components/demo/CustomerApp';
import ThemeToggle from '../components/layout/ThemeToggle';

/** Customer banking app (/bank): a phone-style app for the five demo customers. */
export default function BankApp() {
  return (
    <div className="min-h-screen px-4 py-4 sm:py-8">
      <div className="mx-auto mb-4 flex max-w-md items-center justify-between">
        <Link to="/" className="flex items-center gap-1 text-sm text-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Home
        </Link>
        <span className="text-sm font-semibold">Customer app</span>
        <ThemeToggle />
      </div>
      <CustomerApp />
    </div>
  );
}