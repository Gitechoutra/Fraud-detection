import clsx from 'clsx';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, BellRing, Link2, PhoneCall, ShieldCheck, ShieldX, Smartphone } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ThemeToggle from '../components/layout/ThemeToggle';
import PipelineAnimation from '../components/risk/PipelineAnimation';
import useAuth from '../hooks/useAuth';
import { RULE_CODES, RULES } from '../utils/ruleInfo';

const STORY = [
  { icon: Link2, title: 'A fake message', text: 'Ravi gets an SMS: “Your KYC expires today. Update here.” The link is fake, and he types his bank password into it.' },
  { icon: Smartphone, title: 'The scammer logs in', text: 'Minutes later, someone logs in to Ravi’s account from a new phone in Delhi and adds a new payee.' },
  { icon: PhoneCall, title: 'The OTP trick', text: 'He tries to send ₹48,000 and calls Ravi: “Sir, please tell me the OTP you just received.”' },
  { icon: ShieldCheck, title: 'No OTP is ever sent', text: 'FraudShield sees a new phone, a new payee and a strange city — so it does not create an OTP at all. There is nothing to share.' },
  { icon: BellRing, title: '“Was this you?”', text: 'Ravi’s own phone asks him to approve. He taps NO. The payment is blocked and the scammer’s phone is reported.' },
];

function Story() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((x) => (x + 1) % STORY.length), 4200);
    return () => clearInterval(id);
  }, []);
  const s = STORY[i];
  const Icon = s.icon;
  return (
    <div className="card overflow-hidden p-6 sm:p-8">
      <div className="mb-6 flex gap-2" role="tablist" aria-label="Story steps">
        {STORY.map((step, n) => (
          <button
            key={step.title}
            role="tab"
            aria-selected={n === i}
            aria-label={`Step ${n + 1}: ${step.title}`}
            onClick={() => setI(n)}
            className={clsx('h-1.5 flex-1 rounded-full transition-colors', n <= i ? 'bg-primary' : 'bg-line')}
          />
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={i} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.3 }} className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <span className={clsx('w-fit rounded-2xl p-4', i >= 3 ? 'bg-approved-soft text-approved' : 'bg-blocked-soft text-blocked')}>
            <Icon className="h-8 w-8" aria-hidden />
          </span>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Step {i + 1} of 5</p>
            <h3 className="mt-1 text-xl font-semibold">{s.title}</h3>
            <p className="mt-2 text-muted">{s.text}</p>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const target = user ? '/app' : '/login';
  return (
    <div className="min-h-screen overflow-x-hidden">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[28rem] w-[60rem] max-w-full -translate-x-1/2 rounded-full bg-primary/15 blur-3xl" />
      <header className="relative mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <div className="flex items-center gap-2.5">
          <img src="/logo.svg" alt="" className="h-9 w-9" />
          <span className="text-lg font-semibold">FraudShield</span>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link to={target} className="rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium hover:border-primary/50">
            {user ? 'Open dashboard' : 'Sign in'}
          </Link>
        </div>
      </header>

      <main className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <section className="py-12 text-center sm:py-20">
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-approved" /> Every payment checked in milliseconds, before money moves
          </motion.p>
          <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            Stops fraud <span className="text-primary">before</span> your money leaves your account
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mx-auto mt-5 max-w-2xl text-lg text-muted">
            Every card, UPI and net-banking payment is checked against nine simple warning signs. Normal payments go straight through. Suspicious ones are
            paused or stopped — and you are asked, in plain words, “Was this you?”
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="mt-8 flex justify-center">
            <Link to={target} className="inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-3 font-medium text-white shadow-glow transition hover:bg-primary-dark">
              Try the live demo <ArrowRight className="h-4 w-4" />
            </Link>
          </motion.div>
        </section>

        <section className="py-10">
          <h2 className="mb-2 text-2xl font-semibold">How Ravi’s OTP scam was stopped</h2>
          <p className="mb-6 text-muted">The most common bank fraud in India — and why FraudShield never lets it reach the OTP.</p>
          <Story />
        </section>

        <section className="py-10">
          <h2 className="mb-2 text-2xl font-semibold">Nine protections, in plain words</h2>
          <p className="mb-6 text-muted">Each payment is compared with the account’s own history. Every warning sign adds points; enough points pause or stop it.</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {RULE_CODES.map((code, i) => {
              const r = RULES[code];
              const Icon = r.icon;
              return (
                <motion.div
                  key={code}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-40px' }}
                  transition={{ delay: (i % 3) * 0.05 }}
                  className="card p-5"
                >
                  <span className="mb-3 inline-flex rounded-xl bg-primary-soft p-2.5 text-primary">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <h3 className="font-semibold">{r.name}</h3>
                  <p className="mt-1 text-sm text-muted">{r.what}</p>
                  <p className="mt-3 rounded-xl bg-surface2/70 px-3 py-2 text-xs">{r.example}</p>
                </motion.div>
              );
            })}
          </div>
        </section>

        <section className="py-10">
          <h2 className="mb-2 text-2xl font-semibold">How it works</h2>
          <p className="mb-6 text-muted">Six steps, all inside one database transaction — a payment can never be saved without its decision.</p>
          <div className="card p-5">
            <PipelineAnimation status="BLOCKED" />
          </div>
        </section>

        <section className="py-16 text-center">
          <div className="card mx-auto max-w-2xl p-8">
            <ShieldX className="mx-auto mb-3 h-10 w-10 text-blocked" aria-hidden />
            <h2 className="text-2xl font-semibold">See it catch fraud live</h2>
            <p className="mt-2 text-muted">Play the scam on two phones, run each fraud story in the Fraud Lab, and watch payments being decided in real time.</p>
            <Link to={target} className="mt-6 inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-3 font-medium text-white hover:bg-primary-dark">
              Try the live demo <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>
      <footer className="border-t border-line py-6 text-center text-xs text-muted">
        FraudShield · SQL-based real-time fraud detection · M.Tech project demo with synthetic data
      </footer>
    </div>
  );
}
