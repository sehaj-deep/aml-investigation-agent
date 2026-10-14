import { Tag, Tooltip } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, QuestionCircleFilled } from '@ant-design/icons'
import type { CaseStatus } from '../api'

const STATUS: Record<CaseStatus, { color: string; text: string }> = {
  queued: { color: 'default', text: 'Queued' },
  running: { color: 'processing', text: 'AI investigating' },
  pending_review: { color: 'orange', text: 'Awaiting review' },
  decision_recorded: { color: 'processing', text: 'Applying decision' },
  approved: { color: 'blue', text: 'Decided: approved' },
  rejected: { color: 'purple', text: 'Decided: rejected' },
  failed: { color: 'magenta', text: 'Failed' },
}

export function StatusTag({ status }: { status: CaseStatus }) {
  const s = STATUS[status] ?? { color: 'default', text: status }
  return <Tag color={s.color}>{s.text}</Tag>
}

const ACTION: Record<string, { color: string; text: string }> = {
  escalate: { color: 'volcano', text: 'Escalate' },
  close: { color: 'green', text: 'Close' },
  needs_more_info: { color: 'gold', text: 'Needs more info' },
}

export function ActionTag({ action }: { action: string | null | undefined }) {
  if (!action) return <Tag>None yet</Tag>
  const a = ACTION[action] ?? { color: 'default', text: action }
  return <Tag color={a.color}>{a.text}</Tag>
}

export function PatternTag({ pattern }: { pattern: string | null | undefined }) {
  if (!pattern) return <Tag>None yet</Tag>
  return <Tag color={pattern === 'none' ? 'default' : 'geekblue'}>{pattern}</Tag>
}

export function VerifiedBadge({ faithful }: { faithful: boolean | null | undefined }) {
  if (faithful === null || faithful === undefined)
    return (
      <Tooltip title="Not verified yet">
        <QuestionCircleFilled style={{ color: '#a0aec0' }} />
      </Tooltip>
    )
  return faithful ? (
    <Tooltip title="Every cited transaction exists and matches the data">
      <CheckCircleFilled style={{ color: '#2f855a' }} />
    </Tooltip>
  ) : (
    <Tooltip title="Verification failed: see warnings">
      <CloseCircleFilled style={{ color: '#c53030' }} />
    </Tooltip>
  )
}
