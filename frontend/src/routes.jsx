import { lazy } from 'react';
import { AppLayout, RequireRole } from './App';

const Landing = lazy(() => import('./pages/Landing'));
const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LiveMonitor = lazy(() => import('./pages/LiveMonitor'));
const TransactionDetail = lazy(() => import('./pages/TransactionDetail'));
const Alerts = lazy(() => import('./pages/Alerts'));
const CaseView = lazy(() => import('./pages/CaseView'));
const Rules = lazy(() => import('./pages/Rules'));
const FraudLab = lazy(() => import('./pages/FraudLab'));
const OtpShieldDemo = lazy(() => import('./pages/OtpShieldDemo'));
const Evaluation = lazy(() => import('./pages/Evaluation'));
const Watchlist = lazy(() => import('./pages/Watchlist'));
const AuditLog = lazy(() => import('./pages/AuditLog'));
const Users = lazy(() => import('./pages/Users'));
const NotFound = lazy(() => import('./pages/NotFound'));
const BankApp = lazy(() => import('./pages/BankApp'));
const Attacker = lazy(() => import('./pages/Attacker'));
const DemoSplit = lazy(() => import('./pages/DemoSplit'));

export function buildRoutes() {
  const guard = (role, el) => <RequireRole role={role}>{el}</RequireRole>;
  return [
    { path: '/', element: <Landing /> },
    { path: '/login', element: <Login /> },
    // Customer app and fraudster console use their own logins, not the staff one.
    { path: '/bank', element: <BankApp /> },
    { path: '/attacker', element: <Attacker /> },
    { path: '/demo', element: <DemoSplit /> },
    {
      path: '/app',
      element: <AppLayout />,
      children: [
        { index: true, element: <Dashboard /> },
        { path: 'live', element: <LiveMonitor /> },
        { path: 'transactions/:id', element: <TransactionDetail /> },
        { path: 'alerts', element: <Alerts /> },
        { path: 'cases/:id', element: <CaseView /> },
        { path: 'rules', element: <Rules /> },
        { path: 'lab', element: guard('RISK_MANAGER', <FraudLab />) },
        { path: 'otp-shield', element: <OtpShieldDemo /> },
        { path: 'evaluation', element: guard('RISK_MANAGER', <Evaluation />) },
        { path: 'watchlist', element: <Watchlist /> },
        { path: 'audit', element: guard('RISK_MANAGER', <AuditLog />) },
        { path: 'users', element: guard('ADMIN', <Users />) },
        { path: '*', element: <NotFound /> },
      ],
    },
    { path: '*', element: <NotFound /> },
  ];
}
