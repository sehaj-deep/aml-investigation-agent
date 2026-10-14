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

export const RECOMMENDATION: Record<string, { name: string; color: string }> = {
  escalate: { name: 'Escalate for SAR review', color: 'volcano' },
  close: { name: 'Close: no suspicious activity', color: 'green' },
  needs_more_info: { name: 'More information needed', color: 'gold' },
}

export const DECISION_LABEL = {
  approve: 'Accept AI recommendation',
  reject: 'Override AI recommendation',
  request_more: 'Return for more analysis',
} as const

export const DECISION_PAST = {
  approve: 'Accepted the AI recommendation',
  reject: 'Overrode the AI recommendation',
  request_more: 'Returned the case for more analysis',
} as const
