import { LogOut } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';
import useAuth from '../../hooks/useAuth';
import { titleCase } from '../../utils/format';
import { NAV } from './Sidebar';
import ThemeToggle from './ThemeToggle';

export default function Topbar() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const current =
    NAV.filter((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to))).sort((a, b) => b.to.length - a.to.length)[0];
  const section = current?.label || (pathname.includes('/transactions/') ? 'Payment details' : pathname.includes('/cases/') ? 'Case' : '');

  const onLogout = async () => {
    await logout();
    toast.success('You are logged out');
  };

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/70 backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <img src="/logo.svg" alt="" className="h-7 w-7 lg:hidden" />
          <p className="truncate text-sm font-medium text-muted">{section}</p>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium leading-tight">{user?.full_name}</p>
            <p className="text-[11px] leading-tight text-muted">{titleCase(user?.role)}</p>
          </div>
          <button
            onClick={onLogout}
            className="rounded-xl border border-line bg-surface2 p-2 text-muted transition hover:text-blocked"
            aria-label="Log out"
            title="Log out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
