import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Bell,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  ListX,
  Menu,
  ScrollText,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import useAuth from '../../hooks/useAuth';

export const NAV = [
  { to: '/app', label: 'Dashboard', icon: LayoutDashboard, role: 'ANALYST', end: true },
  { to: '/app/live', label: 'Live Monitor', icon: Activity, role: 'ANALYST' },
  { to: '/app/alerts', label: 'Alerts', icon: Bell, role: 'ANALYST' },
  { to: '/app/rules', label: 'Rules', icon: SlidersHorizontal, role: 'ANALYST' },
  { to: '/app/lab', label: 'Fraud Lab', icon: FlaskConical, role: 'RISK_MANAGER' },
  { to: '/app/otp-shield', label: 'OTP Shield demo', icon: ShieldCheck, role: 'ANALYST' },
  { to: '/app/evaluation', label: 'Evaluation', icon: Gauge, role: 'RISK_MANAGER' },
  { to: '/app/watchlist', label: 'Watchlist', icon: ListX, role: 'ANALYST' },
  { to: '/app/audit', label: 'Audit log', icon: ScrollText, role: 'RISK_MANAGER' },
  { to: '/app/users', label: 'Users', icon: Users, role: 'ADMIN' },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <img src="/logo.svg" alt="" className="h-8 w-8" />
      <div>
        <p className="text-sm font-semibold leading-tight">FraudShield</p>
        <p className="text-[11px] leading-tight text-muted">Real-time fraud protection</p>
      </div>
    </div>
  );
}

function NavItems({ items, onNavigate }) {
  return (
    <nav className="space-y-1" aria-label="Main">
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            clsx(
              'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition',
              isActive ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface2 hover:text-ink',
            )
          }
        >
          <Icon className="h-[18px] w-[18px]" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export default function Sidebar() {
  const { hasRole } = useAuth();
  const items = NAV.filter((n) => hasRole(n.role));
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <>
      {/* Desktop */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-surface/70 px-4 py-5 backdrop-blur-xl lg:flex">
        <Brand />
        <div className="mt-8 flex-1 overflow-y-auto">
          <NavItems items={items} />
        </div>
        <p className="px-3 text-[11px] text-muted">Rules run inside MySQL · decisions in milliseconds</p>
      </aside>

      {/* Mobile bottom bar */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 flex items-center justify-around border-t border-line bg-surface/90 px-2 py-1.5 backdrop-blur-xl lg:hidden"
        aria-label="Quick"
      >
        {items.slice(0, 4).map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx('flex flex-col items-center gap-0.5 rounded-lg px-2 py-1 text-[10px]', isActive ? 'text-primary' : 'text-muted')
            }
          >
            <Icon className="h-5 w-5" aria-hidden />
            {label.split(' ')[0]}
          </NavLink>
        ))}
        <button onClick={() => setOpen(true)} className="flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] text-muted">
          <Menu className="h-5 w-5" aria-hidden />
          More
        </button>
      </nav>

      {/* Mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
            <motion.aside
              className="absolute inset-y-0 left-0 w-72 border-r border-line bg-surface px-4 py-5"
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ duration: 0.2 }}
            >
              <div className="flex items-center justify-between">
                <Brand />
                <button onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-muted hover:bg-surface2" aria-label="Close menu">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="mt-8">
                <NavItems items={items} onNavigate={() => setOpen(false)} />
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
