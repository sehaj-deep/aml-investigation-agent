// Investigator-facing vocabulary. Internal keys (from the dataset's simulator) stay in the
// API and evaluation; the UI shows typology names in the language of AML guidance and
// case-management systems.

export const TYPOLOGY: Record<string, { name: string; description: string }> = {
  'fan-out': {
    name: 'Rapid dispersion of funds',
    description: 'One account distributes funds to many recipients in a short period.',
  },
  'fan-in': {
    name: 'Funds concentration (funnel activity)',
    description: 'Many sources pay into one account, which collects the funds.',
  },
  'gather-scatter': {
    name: 'Pass-through account (flow-through)',
    description:
      'Funds collected from many sources are quickly paid out to many recipients; the account mainly moves money through.',
  },
  'scatter-gather': {
    name: 'Layering via intermediaries (split and recombine)',
    description:
      'Funds are split across intermediary accounts, which pass them on to a single destination.',
  },
  cycle: {
    name: 'Round-tripping (circular flow)',
    description: 'Funds leave an account and return to it through one or more intermediaries.',
  },
  random: {
    name: 'Layering chain (rapid movement of funds)',
    description: 'Funds are passed along a chain of accounts, each forwarding most of what it received.',
  },
  bipartite: {
    name: 'Coordinated multi-party transfers',
    description: 'A group of sending accounts pays a group of receiving accounts.',
  },
  stack: {
    name: 'Multi-layer layering network',
    description: 'Several layers of coordinated transfers between groups of accounts.',
  },
  none: {
    name: 'No typology identified',
    description: 'The activity is consistent with ordinary behavior.',
  },
}

export function typologyName(key: string | null | undefined): string {
  if (!key) return 'Not assessed yet'
  return TYPOLOGY[key]?.name ?? key
}

export const RISK_RULES: Record<string, { title: string; description: string }> = {
  R1: {
    title: 'Currency conversion pass-through',
    description: 'Receives funds in one currency and pays out only in other currencies.',
  },
  R2: { title: 'Flow-through activity', description: 'Both receives and pays out funds in the review period.' },
  R3: {
    title: 'Predominantly new counterparties',
    description: 'At least 90% of counterparties in the review period were never seen before it.',
  },
  R4: {
    title: 'Predominantly one-time relationships',
    description: 'At least 70% of counterparties transact only once or twice in the review period.',
  },
  R5: {
    title: 'Activity concentrated in the review period',
    description: "At least 70% of the account's transactions fall in the review period.",
  },
  R6: {
    title: 'Rapid onward transfers',
    description: 'At least half of incoming transfers are followed by an outgoing payment within 24 hours.',
  },
}

export const RECOMMENDATION: Record<string, { name: string; color: string }> = {
  escalate: { name: 'Escalate for SAR review', color: 'volcano' },
  close: { name: 'Close: no suspicious activity', color: 'green' },
  needs_more_info: { name: 'More information needed', color: 'gold' },
}

// Analyst outcomes, then the supervisor's answer to an escalation (four-eyes rule).
export const DECISION_LABEL = {
  close: 'Close: false alarm',
  escalate: 'Escalate for SAR review',
  request_more: 'Needs more information',
  confirm_escalation: 'Confirm escalation',
  return_to_analyst: 'Return to analyst',
} as const

export const DECISION_PAST = {
  close: 'Closed the alert as a false alarm',
  escalate: 'Escalated for SAR review',
  request_more: 'Asked the AI for more analysis',
  confirm_escalation: 'Confirmed the escalation',
  return_to_analyst: 'Returned the escalation to the analyst',
} as const

// Alert priority from transaction monitoring. Every alert is worked; the band only
// orders the queue. Shares are from the model's validation period.
export const PRIORITY: Record<
  'high' | 'medium' | 'low' | 'sample',
  { name: string; color: string; description: string }
> = {
  high: {
    name: 'High',
    color: '#c53030',
    description: 'Highest risk: in testing, about 9 in 10 payments flagged at this level were laundering.',
  },
  medium: {
    name: 'Medium',
    color: '#dd6b20',
    description: 'Elevated risk: in testing, about half of the payments flagged at this level were laundering.',
  },
  low: {
    name: 'Low',
    color: '#718096',
    description: 'Lower risk, still alerted: most of these are false alarms, as in any bank monitoring.',
  },
  sample: {
    name: 'Below the line',
    color: '#2b6cb0',
    description:
      'Below-the-line testing: a random sample of accounts scored just under the alert threshold, reviewed to measure what monitoring misses.',
  },
}

// A detection reason in plain words, with its value when the value is a count or a size
// (yes/no reasons such as "payment by ACH" need no value).
const YES_NO = /^(format_|cross_currency$|same_bank$|self_transfer$|[sr]_(receives_and_pays|currency_switch)$)/

export function factorText(f: { feature: string; label: string; value: number | null }): string {
  if (f.value === null || YES_NO.test(f.feature)) return f.label
  return `${f.label}: ${Number(f.value.toFixed(2)).toLocaleString()}`
}
