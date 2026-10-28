import { AnimatePresence } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { Suspense } from 'react';
import { Toaster } from 'react-hot-toast';
import { Navigate, Outlet, useLocation, useRoutes } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import Topbar from './components/layout/Topbar';
import useAuth from './hooks/useAuth';
import { buildRoutes } from './routes';

function Loading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center text-muted">
      <Loader2 className="h-6 w-6 animate-spin" aria-label="Loading" />
    </div>
  );
}

/** Logged-in layout: sidebar + glass top bar + animated page outlet. */
export function AppLayout() {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="lg:pl-64">
        <Topbar />
        <main>
          <Suspense fallback={<Loading />}>
            <AnimatePresence mode="wait">
              <Outlet key={location.pathname} />
            </AnimatePresence>
          </Suspense>
        </main>
      </div>
    </div>
  );
}

/** Blocks a page for roles that can't use it (the API enforces it too). */
export function RequireRole({ role, children }) {
  const { hasRole } = useAuth();
  if (!hasRole(role)) return <Navigate to="/app" replace />;
  return children;
}

export default function App() {
  const element = useRoutes(buildRoutes());
  return (
    <>
      <Suspense fallback={<Loading />}>{element}</Suspense>
      <Toaster
        position="top-right"
        toastOptions={{
          className: '!bg-surface !text-ink !border !border-line !rounded-xl !text-sm !shadow-soft',
          duration: 3500,
        }}
      />
    </>
  );
}
