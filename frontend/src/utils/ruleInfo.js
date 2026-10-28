import {
  BadgeIndianRupee,
  Zap,
  Plane,
  Smartphone,
  Moon,
  UserX,
  Scissors,
  BedDouble,
  MessageSquareWarning,
  ShoppingBag,
} from 'lucide-react';

/**
 * Plain-English information for each rule: what it means, why it matters,
 * and a real-life example. Used across the app so every rule is explained
 * the same way.
 */
export const RULES = {
  R1: {
    icon: BadgeIndianRupee,
    name: 'Unusually large amount',
    what: 'The payment is many times bigger than what this person normally spends.',
    why: 'Thieves try to take as much as possible in one go.',
    example: 'Priya usually spends about ₹2,000. Suddenly ₹40,000 is spent on her card at an electronics shop.',
  },
  R2: {
    icon: Zap,
    name: 'Too many payments too fast',
    what: 'Many payments are made from one account within a few minutes.',
    why: 'Fraudsters test stolen cards with quick small payments before a big one.',
    example: 'Six online payments of ₹199 in five minutes, at 2 PM on a weekday.',
  },
  R3: {
    icon: Plane,
    name: 'Impossible travel',
    what: 'The card was used in two far-apart cities within minutes.',
    why: 'Nobody can travel that fast, so the card details are probably stolen.',
    example: 'The card was used in Hyderabad and then in Mumbai 20 minutes later.',
  },
  R4: {
    icon: Smartphone,
    name: 'New device, big amount',
    what: 'A large payment comes from a phone or computer never used before.',
    why: 'A criminal who steals a password logs in from their own phone.',
    example: 'Ravi always uses his Pixel. A ₹30,000 payment comes from an unknown phone.',
  },
  R5: {
    icon: Moon,
    name: 'Late-night large payment',
    what: 'A large payment is made between midnight and 5 AM.',
    why: 'Fraud often happens while the owner is asleep and can’t notice.',
    example: '₹15,000 is transferred at 2:30 AM from an account that is never used at night.',
  },
  R6: {
    icon: UserX,
    name: 'Known fraudster',
    what: 'The phone, internet address, shop or receiving account is on our fraud list.',
    why: 'If it was used for fraud before, it is very likely being used again.',
    example: 'The money is going to an account already reported by 14 scam victims.',
  },
  R7: {
    icon: Scissors,
    name: 'Splitting money to dodge limits',
    what: 'Several payments just under ₹50,000 are made in one day.',
    why: 'Breaking a big amount into pieces is a trick to avoid extra checks.',
    example: 'Three payments of ₹49,500, ₹48,000 and ₹49,900 within a few hours.',
  },
  R8: {
    icon: BedDouble,
    name: 'Sleeping account wakes up',
    what: 'An account unused for six months suddenly sends a lot of money.',
    why: 'Forgotten accounts are easy targets because nobody is watching them.',
    example: 'An old savings account, untouched since last year, sends ₹50,000.',
  },
  R9: {
    icon: MessageSquareWarning,
    name: 'OTP / phishing-link fraud',
    what: 'Money goes to a brand-new payee right after a login from a new phone.',
    why: 'This is exactly how “share your OTP” and fake-link scams work.',
    example:
      'A caller says “your KYC is expiring”, gets Ravi’s OTP, logs in from Delhi and adds a new payee.',
  },
};

export const RULE_CODES = Object.keys(RULES);

export const NORMAL_SCENARIO = {
  icon: ShoppingBag,
  name: 'Normal payment',
  what: 'A customer buys groceries near home, like any other day.',
};

export const DECISIONS = {
  APPROVED: { label: 'Approved', simple: 'Looks normal — the payment went through.', color: '#10B981' },
  REVIEW: { label: 'Held for review', simple: 'Paused for a quick check before any money moves.', color: '#F59E0B' },
  BLOCKED: { label: 'Blocked', simple: 'Stopped — the money never left the account.', color: '#EF4444' },
  PENDING: { label: 'Checking', simple: 'Being checked right now.', color: '#6366F1' },
};

/** Live sentence for the Rules console: "Flag when more than 5 payments in 10 minutes". */
export function rulePreview(code, p) {
  const n = (v) => (v == null ? '?' : Number(v).toLocaleString('en-IN'));
  const r = (v) => `₹${n(v)}`;
  switch (code) {
    case 'R1':
      return `Flag when a payment is more than ${n(p[0])}× the average of the last ${n(p[2])} days (needs ${n(p[1])}+ past payments).`;
    case 'R2':
      return `Flag when more than ${n(p[0])} payments happen in ${n(p[1])} minutes.`;
    case 'R3':
      return `Flag when the city changes within ${n(p[0])} minutes of the previous payment.`;
    case 'R4':
      return `Flag payments above ${r(p[0])} from a device never seen on the account.`;
    case 'R5':
      return `Flag payments above ${r(p[2])} between ${n(p[0])}:00 and ${n(p[1])}:00.`;
    case 'R6':
      return 'Flag any payment whose device, internet address, shop or receiving account is on the watchlist.';
    case 'R7':
      return `Flag when ${n(p[0])}+ payments between ${r(p[1])} and ${r(p[2])} happen within ${n(p[3])} hours.`;
    case 'R8':
      return `Flag payments above ${r(p[1])} from accounts idle for ${n(p[0])}+ days.`;
    case 'R9':
      return `Flag payments of ${r(p[2])}+ to payees newer than ${n(p[0])} hours, within ${n(p[1])} minutes of a risky login or SIM change.`;
    default:
      return '';
  }
}
