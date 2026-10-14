import { Tag, Tooltip } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, QuestionCircleFilled } from '@ant-design/icons'
import type { CaseStatus } from '../api'
import { RECOMMENDATION, TYPOLOGY } from '../terms'

const STATUS: Record<CaseStatus, { color: string; text: string }> = {
  queued: { color: 'default', text: 'New' },
  running: { color: 'processing', text: 'Automated review in progress' },
  pending_review: { color: 'orange', text: 'Pending analyst review' },
  decision_recorded: { color: 'processing', text: 'Applying decision' },
  approved: { color: 'blue', text: 'Closed: AI recommendation accepted' },
  rejected: { color: 'purple', text: 'Closed: AI recommendation overridden' },
  failed: { color: 'magenta', text: 'Processing error' },
}

export function statusText(status: string): string {
  return STATUS[status as CaseStatus]?.text ?? status
}

export function StatusTag({ status }: { status: CaseStatus }) {
  const s = STATUS[status] ?? { color: 'default', text: status }
  return <Tag color={s.color}>{s.text}</Tag>
}

export function ActionTag({ action }: { action: string | null | undefined }) {
  if (!action) return <Tag>Not assessed yet</Tag>
  const a = RECOMMENDATION[action] ?? { color: 'default', name: action }
  return <Tag color={a.color}>{a.name}</Tag>
}

export function PatternTag({ pattern }: { pattern: string | null | undefined }) {
  if (!pattern) return <Tag>Not assessed yet</Tag>
  const t = TYPOLOGY[pattern]
  const tag = <Tag color={pattern === 'none' ? 'default' : 'geekblue'}>{t?.name ?? pattern}</Tag>
  return t ? <Tooltip title={t.description}>{tag}</Tooltip> : tag
}

const BAND: Record<string, { color: string; text: string }> = {
  high: { color: '#c53030', text: 'High' },
  medium: { color: '#dd6b20', text: 'Medium' },
  low: { color: '#2f855a', text: 'Low' },
}

export function RiskBadge({ score, band }: { score: number | null | undefined; band: string | null | undefined }) {
  if (score === null || score === undefined || !band) return <Tag>Not scored</Tag>
  const b = BAND[band] ?? { color: '#718096', text: band }
  return (
    <Tooltip title="Rules-based risk score: the subject's red flags plus its riskiest first-time counterparty's">
      <Tag color={b.color} style={{ minWidth: 76, textAlign: 'center' }}>
        {b.text} {score}
      </Tag>
    </Tooltip>
  )
}

export function VerifiedBadge({ faithful }: { faithful: boolean | null | undefined }) {
  if (faithful === null || faithful === undefined)
    return (
      <Tooltip title="Supporting transactions not verified yet">
        <QuestionCircleFilled style={{ color: '#a0aec0' }} />
      </Tooltip>
    )
  return faithful ? (
    <Tooltip title="Every supporting transaction exists and matches the source data">
      <CheckCircleFilled style={{ color: '#2f855a' }} />
    </Tooltip>
  ) : (
    <Tooltip title="Verification failed: see warnings">
      <CloseCircleFilled style={{ color: '#c53030' }} />
    </Tooltip>
  )
}
