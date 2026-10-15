import { useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  List,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import { ArrowLeftOutlined, LockOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type CaseDetail, type Decision, type Evidence, type Trigger } from '../api'
import { ActionTag, PatternTag, PriorityTag, StatusTag, VerifiedBadge, statusText } from '../components/badges'
import NetworkGraph from '../components/NetworkGraph'
import CopilotPanel from '../components/CopilotPanel'
import { useUser } from '../user'
import { DECISION_LABEL, DECISION_PAST, RISK_RULES, factorText, typologyName } from '../terms'

const LIVE = new Set(['queued', 'running', 'decision_recorded'])

// Account labels come from the case file (A0 is the subject); the AI's summary uses them.
function labelName(label: string) {
  return label === 'A0' ? 'Subject' : label
}

function useLabels(c: CaseDetail | undefined) {
  return useMemo(() => {
    const m = new Map<string, string>()
    Object.entries(c?.analysis?.aliases ?? {}).forEach(([label, [bank, acct]]) =>
      m.set(`${bank}/${acct}`, label),
    )
    return m
  }, [c])
}

function AccountCell({
  bank,
  account,
  labels,
}: {
  bank: string | number
  account: string
  labels: Map<string, string>
}) {
  const label = labels.get(`${bank}/${account}`)
  return (
    <span className="mono">
      {label && (
        <Tag color={label === 'A0' ? 'orange' : undefined} style={{ marginInlineEnd: 4 }}>
          {labelName(label)}
        </Tag>
      )}
      {bank}/{account}
    </span>
  )
}

function when(ts: string) {
  return dayjs(ts).format('MMM D HH:mm')
}

function amount(value: string, currency: string) {
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`
}

export default function CaseWorkspace() {
  const { caseId = '' } = useParams()
  const navigate = useNavigate()
  const { data: c, isLoading, error } = useQuery({
    queryKey: ['case', caseId],
    queryFn: () => api.case(caseId),
    refetchInterval: (q) => (q.state.data && LIVE.has(q.state.data.status) ? 3000 : false),
  })
  const labels = useLabels(c)
  const [highlightId, setHighlightId] = useState<string>('flagged')
  const [activeTab, setActiveTab] = useState('flagged')
  const [copilotTx, setCopilotTx] = useState<Set<number>>(new Set())

  const triggers = useMemo(() => c?.analysis?.triggers ?? [], [c])
  const candidates = useMemo(() => c?.analysis?.candidates ?? [], [c])
  const evidenceIds = useMemo(() => new Set((c?.draft?.evidence ?? []).map((e) => e.tx_id)), [c])
  const highlight = useMemo(() => {
    const s = new Set<string>()
    if (!c) return s
    const add = (bank: string | number, acct: string) => {
      const l = labels.get(`${bank}/${acct}`)
      if (l) s.add(l)
    }
    if (highlightId === 'flagged') triggers.forEach((t) => (add(t.from_bank, t.from_account), add(t.to_bank, t.to_account)))
    else if (highlightId === 'evidence')
      c.draft?.evidence.forEach((e) => (add(e.from_bank, e.from_account), add(e.to_bank, e.to_account)))
    else if (highlightId === 'copilot') {
      // Accounts on either side of the transactions the copilot cited.
      triggers.filter((t) => copilotTx.has(t.tx_id)).forEach((t) => (add(t.from_bank, t.from_account), add(t.to_bank, t.to_account)))
      c.draft?.evidence
        .filter((e) => copilotTx.has(e.tx_id))
        .forEach((e) => (add(e.from_bank, e.from_account), add(e.to_bank, e.to_account)))
      c.case_graph?.edges
        .filter((e) => e.tx_ids.some((t) => copilotTx.has(t)))
        .forEach((e) => (s.add(e.src), s.add(e.dst)))
    }
    else candidates.find((x) => x.id === highlightId)?.accounts.forEach((a) => s.add(a))
    return s
  }, [c, highlightId, labels, triggers, candidates, copilotTx])

  if (isLoading) return <Spin style={{ margin: 48 }} />
  if (error || !c)
    return (
      <div className="page">
        <Alert type="error" showIcon message={`Could not load the case: ${String(error)}`} />
      </div>
    )

  const seedNode = c.case_graph?.nodes.find((n) => n.label === 'A0')
  const reviewing = LIVE.has(c.status) && !c.draft

  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Card size="small">
          <Space size={16} wrap align="center">
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/alerts')} />
            <Typography.Title level={5} style={{ margin: 0 }} className="mono">
              {c.alert_id}
            </Typography.Title>
            <PriorityTag priority={c.alert.priority} score={c.alert.detection_score} />
            <StatusTag status={c.status} />
            <Descriptions size="small" column={4} style={{ minWidth: 640 }}>
              <Descriptions.Item label="Account">
                <span className="mono">
                  {c.alert.seed_bank}/{c.alert.seed_account}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="Jurisdiction">{seedNode?.jurisdiction ?? 'n/a'}</Descriptions.Item>
              <Descriptions.Item label="Review period">
                {dayjs(c.alert.window_start).format('MMM D HH:mm')} to{' '}
                {dayjs(c.alert.window_end).format('MMM D HH:mm')}
              </Descriptions.Item>
              <Descriptions.Item label="Case">
                <span className="mono">{c.case_id}</span>
              </Descriptions.Item>
            </Descriptions>
            <CopilotPanel
              caseId={c.case_id}
              ready={!!c.analysis?.case_file}
              onCite={(ids) => {
                setCopilotTx(new Set(ids))
                setHighlightId('copilot')
                setActiveTab('network')
              }}
            />
          </Space>
        </Card>

        {reviewing && (
          <Alert
            type="info"
            showIcon
            message="The AI review is in progress (usually about a minute)."
            description="The flagged payments, network and red flags are ready to look at now. The AI assessment appears on the right when it is done."
          />
        )}
        {c.status === 'failed' && <FailedNotice c={c} />}

        <Row gutter={12}>
          <Col xs={24} xl={15}>
            <Card size="small">
              <Tabs
                size="small"
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  {
                    key: 'flagged',
                    label: `Flagged payments (${triggers.length || c.alert.trigger_tx_ids?.length || 0})`,
                    children: <FlaggedPayments triggers={triggers} labels={labels} loading={reviewing} />,
                  },
                  {
                    key: 'network',
                    label: 'Network',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                          <span className="panel-title">Highlight</span>
                          <Select
                            size="small"
                            value={highlightId}
                            onChange={setHighlightId}
                            style={{ width: 340 }}
                            options={[
                              { value: 'flagged', label: 'Accounts in the flagged payments' },
                              { value: 'evidence', label: 'Accounts in the supporting transactions' },
                              ...(copilotTx.size
                                ? [{ value: 'copilot', label: "Accounts in the copilot's cited transactions" }]
                                : []),
                              ...candidates.map((x, i) => ({
                                value: x.id,
                                label: `Pattern ${i + 1}: ${typologyName(x.kind)} (${x.accounts.length} accounts)`,
                              })),
                            ]}
                          />
                        </Space>
                        <NetworkGraph graph={c.case_graph} evidenceTxIds={evidenceIds} highlight={highlight} />
                      </Space>
                    ),
                  },
                  {
                    key: 'evidence',
                    label: `Supporting transactions (${c.draft?.evidence.length ?? 0})`,
                    children: (
                      <Table<Evidence>
                        size="small"
                        rowKey="tx_id"
                        dataSource={c.draft?.evidence ?? []}
                        pagination={{ pageSize: 15, showSizeChanger: false }}
                        locale={{
                          emptyText: (
                            <Empty description={reviewing ? 'The AI review is in progress' : 'No supporting transactions'} />
                          ),
                        }}
                        columns={[
                          { title: 'Time', dataIndex: 'timestamp', render: (v: string) => when(v) },
                          {
                            title: 'From',
                            render: (_, e) => <AccountCell bank={e.from_bank} account={e.from_account} labels={labels} />,
                          },
                          {
                            title: 'To',
                            render: (_, e) => <AccountCell bank={e.to_bank} account={e.to_account} labels={labels} />,
                          },
                          {
                            title: 'Amount',
                            align: 'right',
                            render: (_, e) => <span className="mono">{amount(e.amount_paid, e.currency_paid)}</span>,
                          },
                          { title: 'Reference', dataIndex: 'tx_id', render: (v) => <span className="mono">{v}</span> },
                        ]}
                      />
                    ),
                  },
                  {
                    key: 'patterns',
                    label: `Patterns found (${candidates.length})`,
                    children: (
                      <Table
                        size="small"
                        rowKey="id"
                        dataSource={candidates}
                        pagination={false}
                        locale={{ emptyText: <Empty description="No suspicious structure found among new counterparties" /> }}
                        onRow={(x) => ({ onClick: () => setHighlightId(x.id), style: { cursor: 'pointer' } })}
                        columns={[
                          { title: '#', render: (_, __, i) => `Pattern ${i + 1}` },
                          { title: 'Pattern', dataIndex: 'kind', render: (v) => <PatternTag pattern={v} /> },
                          {
                            title: 'Accounts',
                            dataIndex: 'accounts',
                            render: (v: string[]) => v.map(labelName).join(', '),
                          },
                          { title: 'Payments', render: (_, x) => x.tx_ids.length, align: 'right' },
                          { title: 'Why', dataIndex: 'reason' },
                        ]}
                      />
                    ),
                  },
                  { key: 'history', label: 'History', children: <HistoryTab caseId={c.case_id} /> },
                ]}
              />
            </Card>
          </Col>

          <Col xs={24} xl={9}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <WhyCard c={c} />
              <RedFlagsCard c={c} />
              <AssessmentCard c={c} />
              <DecisionCard key={c.status} c={c} />
            </Space>
          </Col>
        </Row>
      </Space>
    </div>
  )
}

function FailedNotice({ c }: { c: CaseDetail }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api.retry(c.case_id),
    onSuccess: () => {
      message.success('The AI review was restarted')
      queryClient.invalidateQueries({ queryKey: ['case', c.case_id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
    onError: (e) => message.error(String(e)),
  })
  return (
    <Alert
      type="error"
      showIcon
      message="The AI review could not finish"
      description={
        <Space direction="vertical" size={4}>
          <span>
            The evidence gathered so far is kept. Retry the review; it continues from where it
            stopped. If it fails again, the technical detail below helps support.
          </span>
          <Typography.Text type="secondary" className="mono" style={{ fontSize: 11 }}>
            {c.error}
          </Typography.Text>
        </Space>
      }
      action={
        <Button type="primary" danger loading={retry.isPending} onClick={() => retry.mutate()}>
          Retry the AI review
        </Button>
      }
    />
  )
}

function FlaggedPayments({
  triggers,
  labels,
  loading,
}: {
  triggers: Trigger[]
  labels: Map<string, string>
  loading: boolean
}) {
  return (
    <Table<Trigger>
      size="small"
      rowKey="tx_id"
      dataSource={triggers}
      pagination={{ pageSize: 15, showSizeChanger: false }}
      locale={{ emptyText: <Empty description={loading ? 'Loading the flagged payments' : 'No flagged payments'} /> }}
      columns={[
        { title: 'Time', dataIndex: 'timestamp', render: (v: string) => when(v) },
        { title: 'From', render: (_, t) => <AccountCell bank={t.from_bank} account={t.from_account} labels={labels} /> },
        { title: 'To', render: (_, t) => <AccountCell bank={t.to_bank} account={t.to_account} labels={labels} /> },
        {
          title: 'Paid',
          align: 'right',
          render: (_, t) => <span className="mono">{amount(t.amount_paid, t.currency_paid)}</span>,
        },
        {
          title: 'Received',
          align: 'right',
          render: (_, t) =>
            t.currency_received === t.currency_paid ? (
              <Typography.Text type="secondary">same</Typography.Text>
            ) : (
              <span className="mono">{amount(t.amount_received, t.currency_received)}</span>
            ),
        },
        { title: 'Payment type', dataIndex: 'payment_format' },
        { title: 'Reference', dataIndex: 'tx_id', render: (v) => <span className="mono">{v}</span> },
      ]}
    />
  )
}

function WhyCard({ c }: { c: CaseDetail }) {
  const factors = c.alert.detection_factors ?? []
  return (
    <Card size="small" title={<span className="panel-title">Why this alert</span>}>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Typography.Text>
          {c.alert.priority === 'sample'
            ? `Below-the-line sample: this account scored just under the alert threshold and was picked at random for review. Its ${c.alert.trigger_tx_ids?.length ?? 0} strongest payment(s) are listed. Main reasons for the top one:`
            : `Transaction monitoring flagged ${c.alert.trigger_tx_ids?.length ?? 0} payment(s) on this account. Main reasons for the strongest one:`}
        </Typography.Text>
        {factors.length === 0 ? (
          <Typography.Text type="secondary">No reasons recorded</Typography.Text>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: 18 }}>
            {factors.map((f) => (
              <li key={f.feature}>{factorText(f)}</li>
            ))}
          </ul>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          These are statistical reasons, not proof. As in any bank monitoring, most alerts are
          false alarms.
        </Typography.Text>
      </Space>
    </Card>
  )
}

function RuleList({ codes }: { codes: string[] }) {
  if (codes.length === 0) return <Typography.Text type="secondary">None</Typography.Text>
  return (
    <ul style={{ margin: 0, paddingInlineStart: 18 }}>
      {codes.map((code) => (
        <li key={code} style={{ fontSize: 13 }}>
          <b>{RISK_RULES[code]?.title ?? code}</b>
          <Typography.Text type="secondary"> {RISK_RULES[code]?.description}</Typography.Text>
        </li>
      ))}
    </ul>
  )
}

function RedFlagsCard({ c }: { c: CaseDetail }) {
  const risk = c.analysis?.risk
  return (
    <Card size="small" title={<span className="panel-title">Red flags</span>}>
      {!risk ? (
        <Empty description={LIVE.has(c.status) ? 'Checking red flags' : 'Not checked'} />
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <div>
            <div className="panel-title" style={{ marginBottom: 4 }}>
              Subject account
            </div>
            <RuleList codes={risk.subject.rules} />
          </div>
          {risk.top_counterparty && risk.top_counterparty.score > 0 && (
            <div>
              <div className="panel-title" style={{ marginBottom: 4 }}>
                Riskiest new counterparty ({labelName(risk.top_counterparty.label)})
              </div>
              <RuleList codes={risk.top_counterparty.rules} />
            </div>
          )}
        </Space>
      )}
    </Card>
  )
}

function AssessmentCard({ c }: { c: CaseDetail }) {
  const d = c.draft
  const hyp = c.analysis?.hypothesis
  return (
    <Card size="small" title={<span className="panel-title">AI assessment (advisory)</span>}>
      {!d ? (
        <Empty description={LIVE.has(c.status) ? 'The AI review is in progress' : 'No assessment'} />
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space wrap>
            <span>Recommendation</span>
            <ActionTag action={d.recommended_action} />
            <span>Confidence</span>
            <Tag>{d.confidence}</Tag>
          </Space>
          <Space wrap>
            <span>Suspected pattern</span>
            <PatternTag pattern={d.pattern_hypothesis} />
          </Space>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{d.summary}</Typography.Paragraph>
          {hyp?.rationale && (
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              <b>Reasoning:</b> {hyp.rationale}
            </Typography.Paragraph>
          )}
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            <b>Not checked:</b> {d.limitations}
          </Typography.Paragraph>
          <Space>
            <VerifiedBadge faithful={c.verification?.faithful} />
            <span>
              {c.verification
                ? c.verification.faithful
                  ? `All ${c.verification.evidence_rows} supporting transactions match the bank's records`
                  : 'Some supporting transactions do not match the bank records'
                : 'Supporting transactions not checked yet'}
            </span>
          </Space>
          {c.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`${c.warnings.length} warning(s)`}
              description={
                <ul style={{ paddingInlineStart: 16, margin: 0 }}>
                  {c.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}
        </Space>
      )}
    </Card>
  )
}

const ANALYST_OPTIONS = ['close', 'escalate', 'request_more'] as const
const SUPERVISOR_OPTIONS = ['confirm_escalation', 'return_to_analyst'] as const

function DecisionCard({ c }: { c: CaseDetail }) {
  const user = useUser()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const awaiting = c.status === 'pending_approval'
  const [action, setAction] = useState<Decision['action'] | null>(null)
  const [reason, setReason] = useState('')
  const decide = useMutation({
    mutationFn: () => api.decide(c.case_id, action!, reason, user.name, user.role),
    onSuccess: () => {
      message.success('Decision recorded')
      setReason('')
      setAction(null)
      queryClient.invalidateQueries({ queryKey: ['case', c.case_id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
    onError: (e) => message.error(String(e)),
  })

  const ai = c.draft?.recommended_action
  const escalator = [...c.decisions].reverse().find((d) => d.action === 'escalate')?.reviewer
  // The server enforces the four-eyes rule; the screen explains it before you try.
  const blocked = awaiting && (user.role !== 'supervisor' || escalator === user.name)
  const canDecide = c.status === 'pending_review' || awaiting
  const options = awaiting ? SUPERVISOR_OPTIONS : ANALYST_OPTIONS
  const agrees =
    action === 'close' ? ai === 'close' : action === 'escalate' ? ai === 'escalate' : null

  return (
    <Card size="small" title={<span className="panel-title">Your decision</span>}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {c.decisions.length > 0 && (
          <List
            size="small"
            dataSource={c.decisions}
            renderItem={(d) => (
              <List.Item>
                <Space direction="vertical" size={0}>
                  <span>
                    <b>{DECISION_PAST[d.action]}</b> by {d.reviewer}
                  </span>
                  <Typography.Text type="secondary">
                    {dayjs(d.decided_at).format('YYYY-MM-DD HH:mm')}: {d.reason}
                  </Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        )}
        {canDecide ? (
          <>
            {awaiting ? (
              <Alert
                type={blocked ? 'warning' : 'info'}
                showIcon
                icon={<LockOutlined />}
                message="This escalation needs a supervisor's approval (four-eyes rule)."
                description={
                  blocked
                    ? 'A supervisor other than the person who escalated must confirm or return it. Switch to the Supervisor role at the top right.'
                    : 'Confirm the escalation, or return it to the analyst with a reason.'
                }
              />
            ) : (
              <Space wrap>
                <span>AI recommendation</span>
                <ActionTag action={ai} />
              </Space>
            )}
            <Radio.Group
              value={action}
              onChange={(e) => setAction(e.target.value)}
              optionType="button"
              disabled={blocked}
              options={options.map((o) => ({ value: o, label: DECISION_LABEL[o] }))}
            />
            {agrees !== null && (
              <Typography.Text type="secondary">
                {agrees ? 'This agrees with the AI recommendation.' : 'This differs from the AI recommendation.'}
              </Typography.Text>
            )}
            {action === 'escalate' && (
              <Typography.Text type="secondary">
                A supervisor will confirm the escalation before the case closes.
              </Typography.Text>
            )}
            <Input.TextArea
              rows={3}
              disabled={blocked}
              placeholder="Reason for your decision (required, kept in the case history)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button
              type="primary"
              block
              disabled={!action || reason.trim().length < 3 || blocked}
              loading={decide.isPending}
              onClick={() => decide.mutate()}
            >
              Record decision as {user.name}
            </Button>
          </>
        ) : (
          <Typography.Text type="secondary">
            {LIVE.has(c.status)
              ? 'You can decide once the AI review is done.'
              : c.status === 'failed'
                ? 'Retry the AI review (top of the page) before deciding.'
                : 'This case is closed. Recorded decisions cannot be changed.'}
          </Typography.Text>
        )}
      </Space>
    </Card>
  )
}

// Plain-language case history from the audit log; technical events on request.
const STEP_TEXT: Record<string, string> = {
  triage: "Gathered the account's activity, network and red flags",
  hypothesize: 'AI identified the suspected pattern',
  collect_evidence: 'Collected the supporting transactions',
  draft: 'AI wrote the assessment and recommendation',
  verify: "Checked every supporting transaction against the bank's records",
  human_review: 'Waiting for an analyst decision',
  finalize: 'Case closed',
}

type AuditEvent = {
  seq: number
  event_type: string
  actor: string
  created_at: string
  payload: Record<string, unknown>
}

function plain(e: AuditEvent): string | null {
  const p = e.payload
  switch (e.event_type) {
    case 'case_created':
      return 'Alert opened; AI review requested'
    case 'node_started':
      return STEP_TEXT[String(p.node)] ?? null
    case 'decision_recorded':
      return `${p.reviewer} ${DECISION_PAST[p.action as Decision['action']]?.toLowerCase() ?? p.action}: ${p.reason}`
    case 'status':
      return p.status === 'failed' ? 'The AI review failed' : `Status: ${statusText(String(p.status))}`
    default:
      return null
  }
}

function technical(e: AuditEvent): string {
  const p = e.payload
  switch (e.event_type) {
    case 'tool_call':
      return `data lookup ${p.name}: ${p.ok ? 'ok' : 'error'}, ${p.duration_ms} ms`
    case 'model_call':
      return `AI model call (${p.model}): ${p.input_tokens} tokens in, ${p.output_tokens} out`
    default:
      return `${e.event_type}${p.node ? ` ${p.node}` : ''}`
  }
}

// Who did a step: the AI only for its own judgments; code steps are the system's.
const AI_STEPS = new Set(['agent', 'hypothesize', 'draft'])

function who(e: AuditEvent): string {
  if (e.event_type === 'model_call') return 'AI'
  if (e.event_type.startsWith('node_')) return AI_STEPS.has(String(e.payload.node)) ? 'AI' : 'system'
  if (e.actor === 'api' || e.actor === 'worker' || e.actor === 'agent') return 'system'
  return e.actor
}

function HistoryTab({ caseId }: { caseId: string }) {
  const [details, setDetails] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['audit', caseId],
    queryFn: () => api.audit(caseId),
    refetchInterval: 5000,
  })
  if (isLoading) return <Spin />
  if (!data) return <Empty />
  const items = data.events
    .map((e) => ({ e, text: plain(e) ?? (details ? technical(e) : null) }))
    .filter((x) => x.text)
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Tag color={data.chain_valid ? 'green' : 'red'}>
          {data.chain_valid ? 'Record verified: not altered' : 'Record integrity check failed'}
        </Tag>
        <Typography.Text type="secondary">Every step is recorded and cannot be edited.</Typography.Text>
        <span style={{ fontSize: 12 }}>
          <Switch size="small" checked={details} onChange={setDetails} /> Show technical details
        </span>
      </Space>
      <div style={{ maxHeight: 520, overflow: 'auto', paddingTop: 8 }}>
        <Timeline
          items={items.map(({ e, text }) => ({
            color: e.event_type.startsWith('decision') ? 'red' : plain(e) ? 'blue' : 'gray',
            children: (
              <span style={{ fontSize: 12 }}>
                {text}{' '}
                <Typography.Text type="secondary">
                  {who(e)},{' '}
                  {dayjs(e.created_at).format('HH:mm:ss')}
                </Typography.Text>
              </span>
            ),
          }))}
        />
      </div>
    </Space>
  )
}
