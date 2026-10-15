import { Tag, Tooltip } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, QuestionCircleFilled } from '@ant-design/icons'
import type { Priority, WorkStatus } from '../api'
import { PRIORITY, RECOMMENDATION, TYPOLOGY } from '../terms'

const STATUS: Record<WorkStatus, { color: string; text: string }> = {
  new: { color: 'default', text: 'New' },
  queued: { color: 'processing', text: 'AI review starting' },
  running: { color: 'processing', text: 'AI review in progress' },
  pending_review: { color: 'orange', text: 'Ready for review' },
  decision_recorded: { color: 'processing', text: 'Applying decision' },
  pending_approval: { color: 'gold', text: 'Awaiting supervisor approval' },
  closed: { color: 'green', text: 'Closed: false alarm' },
  escalated: { color: 'volcano', text: 'Escalated for SAR review' },
  failed: { color: 'magenta', text: 'AI review failed' },
}

export function statusText(status: string): string {
  return STATUS[status as WorkStatus]?.text ?? status
}

export function StatusTag({ status }: { status: WorkStatus }) {
  const s = STATUS[status] ?? { color: 'default', text: status }
  return <Tag color={s.color}>{s.text}</Tag>
}

export function ActionTag({ action }: { action: string | null | undefined }) {
  if (!action) return <Tag>Not reviewed yet</Tag>
  const a = RECOMMENDATION[action] ?? { color: 'default', name: action }
  return <Tag color={a.color}>{a.name}</Tag>
}

export function PatternTag({ pattern }: { pattern: string | null | undefined }) {
  if (!pattern) return <Tag>Not reviewed yet</Tag>
  const t = TYPOLOGY[pattern]
  const tag = <Tag color={pattern === 'none' ? 'default' : 'geekblue'}>{t?.name ?? pattern}</Tag>
  return t ? <Tooltip title={t.description}>{tag}</Tooltip> : tag
}

export function PriorityTag({
  priority,
  score,
}: {
  priority: Priority | null | undefined
  score?: number | null
}) {
  if (!priority) return <Tag>No priority</Tag>
  const p = PRIORITY[priority]
  return (
    <Tooltip title={p.description}>
      <Tag color={p.color} style={{ minWidth: 84, textAlign: 'center' }}>
        {p.name}
        {score !== null && score !== undefined && ` ${Math.round(score * 100)}`}
      </Tag>
    </Tooltip>
  )
}

export function VerifiedBadge({ faithful }: { faithful: boolean | null | undefined }) {
  if (faithful === null || faithful === undefined)
    return (
      <Tooltip title="Supporting transactions not checked yet">
        <QuestionCircleFilled style={{ color: '#a0aec0' }} />
      </Tooltip>
    )
  return faithful ? (
    <Tooltip title="Every supporting transaction exists and matches the bank's records">
      <CheckCircleFilled style={{ color: '#2f855a' }} />
    </Tooltip>
  ) : (
    <Tooltip title="Check failed: see warnings">
      <CloseCircleFilled style={{ color: '#c53030' }} />
    </Tooltip>
  )
}
