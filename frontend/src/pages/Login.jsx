import { motion } from 'framer-motion';
import { Eye, EyeOff, LogIn } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import ThemeToggle from '../components/layout/ThemeToggle';
import Button from '../components/ui/Button';
import useAuth from '../hooks/useAuth';

const DEMO = [
  { username: 'admin', password: 'Admin@123', role: 'Admin — everything' },
  { username: 'risk', password: 'Risk@123', role: 'Risk manager — rules, lab' },
  { username: 'analyst', password: 'Analyst@123', role: 'Analyst — alerts, cases' },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: '', password: '' });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (user) return <Navigate to={location.state?.from || '/app'} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const u = await login(form.username.trim(), form.password);
      toast.success(`Welcome, ${u.full_name.split(' ')[0]}`);
      navigate(location.state?.from || '/app', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="pointer-events-none absolute -top-40 left-1/2 h-96 w-[40rem] -translate-x-1/2 rounded-full bg-primary/20 blur-3xl" />
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="card relative w-full max-w-md p-8"
      >
        <Link to="/" className="mb-6 flex items-center gap-2.5">
          <img src="/logo.svg" alt="" className="h-9 w-9" />
          <span className="text-lg font-semibold">FraudShield</span>
        </Link>
        <h1 className="text-xl font-semibold">Sign in to the control room</h1>
        <p className="mt-1 text-sm text-muted">Watch payments being checked live and investigate anything suspicious.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="username" className="label">
              Username
            </label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
          </div>
          <div>
            <label htmlFor="password" className="label">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                className="input pr-10"
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-muted hover:text-ink"
                aria-label={show ? 'Hide password' : 'Show password'}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          {error && (
            <p role="alert" className="rounded-xl border border-blocked/30 bg-blocked-soft px-3 py-2 text-sm text-blocked">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" size="lg" loading={busy} icon={LogIn}>
            Sign in
          </Button>
        </form>

        <div className="mt-6 rounded-2xl border border-line bg-surface2/60 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Demo logins — tap to fill</p>
          <div className="space-y-1.5">
            {DEMO.map((d) => (
              <button
                key={d.username}
                type="button"
                onClick={() => setForm({ username: d.username, password: d.password })}
                className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface"
              >
                <span className="mono">
                  {d.username} / {d.password}
                </span>
                <span className="text-xs text-muted">{d.role}</span>
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
