import { Clock, ShieldX, UserCheck } from 'lucide-react';
import Badge from '../ui/Badge';

const RESPONSES = {
  WAITING: { label: 'Waiting', tone: 'neutral', icon: Clock, help: 'The customer has not answered in the banking app yet.' },
  CONFIRMED_ME: { label: 'This was me', tone: 'approved', icon: UserCheck, help: 'The customer confirmed with their password; a held payment was completed.' },
  REPORTED_NOT_ME: { label: 'Not me', tone: 'blocked', icon: ShieldX, help: 'The customer reported fraud; held money was released and the device, IP and payee blocked.' },
};

/** The customer's answer in the banking app, for staff screens. */
export default function CustomerResponseBadge({ response, withHelp = false }) {
  const r = RESPONSES[response] || RESPONSES.WAITING;
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <Badge tone={r.tone} icon={r.icon}>
        Customer: {r.label}
      </Badge>
      {withHelp && <span className="text-xs text-muted">{r.help}</span>}
    </span>
  );
}
