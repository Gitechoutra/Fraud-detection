import { Compass } from 'lucide-react';
import { Link } from 'react-router-dom';
import EmptyState from '../components/ui/EmptyState';

export default function NotFound() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <EmptyState
        icon={Compass}
        title="This page doesn't exist"
        text="The link may be old or mistyped. Let's take you somewhere useful."
        action={
          <Link to="/app" className="mt-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white">
            Go to the dashboard
          </Link>
        }
      />
    </div>
  );
}
