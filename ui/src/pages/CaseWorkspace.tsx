import { useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Badge,
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
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import { ArrowLeftOutlined, LockOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type CaseDetail, type Decision, type Evidence } from '../api'
import { ActionTag, PatternTag, StatusTag, VerifiedBadge } from '../components/badges'
import NetworkGraph from '../components/NetworkGraph'
import { useUser } from '../user'
import { DECISION_LABEL, DECISION_PAST, typologyName } from '../terms'

const LIVE = new Set(['queued', 'running', 'decision_recorded'])

function useLabels(c: CaseDetail | undefined) {
  return useMemo(() => {
    const m = new Map<string, string>()
    Object.entries(c?.analysis?.aliases ?? {}).forEach(([label, [bank, acct]]) =>
      m.set(`${bank}/${acct}`, label),
    )
    return m
  }, [c])
}

function AccountCell({ bank, account, labels }: { bank: string; account: string; labels: Map<string, string> }) {
  const label = labels.get(`${bank}/${account}`)
  return (
    <span className="mono">
      {label && <Tag style={{ marginInlineEnd: 4 }}>{label}</Tag>}
      {bank}/{account}
    </span>
  )
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
  const [highlightId, setHighlightId] = useState<string>('evidence')

  const evidenceIds = useMemo(() => new Set((c?.draft?.evidence ?? []).map((e) => e.tx_id)), [c])
  const highlight = useMemo(() => {
    if (!c) return new Set<string>()
    if (highlightId === 'evidence') {
      const s = new Set<string>()
      c.draft?.evidence.forEach((e) => {
        const a = labels.get(`${e.from_bank}/${e.from_account}`)
        const b = labels.get(`${e.to_bank}/${e.to_account}`)
        if (a) s.add(a)
        if (b) s.add(b)
      })
      return s
    }
    const cand = c.analysis?.candidates.find((x) => x.id === highlightId)
    return new Set(cand?.accounts ?? [])
  }, [c, highlightId, labels])

  if (isLoading) return <Spin style={{ margin: 48 }} />
  if (error || !c)
    return (
      <div className="page">
        <Alert type="error" showIcon message={`Could not load case: ${String(error)}`} />
      </div>
    )

  const seedNode = c.case_graph?.nodes.find((n) => n.label === 'A0')

  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Card size="small">
          <Space size={16} wrap align="center">
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/cases')} />
            <Typography.Title level={5} style={{ margin: 0 }} className="mono">
              {c.case_id}
            </Typography.Title>
            <StatusTag status={c.status} />
            {LIVE.has(c.status) && <Badge status="processing" text="updating" />}
            <Descriptions size="small" column={5} style={{ minWidth: 760 }}>
              <Descriptions.Item label="Alert">
                <span className="mono">{c.alert_id}</span>
              </Descriptions.Item>
              <Descriptions.Item label="Subject">
                <span className="mono">
                  {c.alert.seed_bank}/{c.alert.seed_account}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="Jurisdiction">{seedNode?.jurisdiction ?? 'n/a'}</Descriptions.Item>
              <Descriptions.Item label="Window">
                {dayjs(c.alert.window_start).format('MM-DD HH:mm')} to{' '}
                {dayjs(c.alert.window_end).format('MM-DD HH:mm')}
              </Descriptions.Item>
              <Descriptions.Item label="Model">
                {c.model ?? 'n/a'} {c.prompt_version && <Tag>{c.prompt_version}</Tag>}
              </Descriptions.Item>
            </Descriptions>
          </Space>
        </Card>

        {c.status === 'failed' && <Alert type="error" showIcon message="Case failed" description={c.error} />}

        <Row gutter={12}>
          <Col xs={24} xl={15}>
            <Card size="small">
              <Tabs
                size="small"
                items={[
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
                            style={{ width: 320 }}
                            options={[
                              { value: 'evidence', label: 'Accounts in the supporting transactions' },
                              ...(c.analysis?.candidates ?? []).map((x) => ({
                                value: x.id,
                                label: `${x.id}: ${typologyName(x.kind)} (${x.accounts.length} accounts)`,
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
                        locale={{ emptyText: <Empty description="No supporting transactions" /> }}
                        columns={[
                          { title: 'Tx', dataIndex: 'tx_id', render: (v) => <span className="mono">{v}</span> },
                          { title: 'Time', dataIndex: 'timestamp' },
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
                            render: (_, e) => (
                              <span className="mono">
                                {Number(e.amount_paid).toLocaleString(undefined, { maximumFractionDigits: 6 })}{' '}
                                {e.currency_paid}
                              </span>
                            ),
                          },
                        ]}
                      />
                    ),
                  },
                  {
                    key: 'candidates',
                    label: `Typology indicators (${c.analysis?.candidates.length ?? 0})`,
                    children: (
                      <Table
                        size="small"
                        rowKey="id"
                        dataSource={c.analysis?.candidates ?? []}
                        pagination={false}
                        locale={{ emptyText: <Empty description="No indicators: no first-time counterparty structure found" /> }}
                        onRow={(x) => ({ onClick: () => setHighlightId(x.id), style: { cursor: 'pointer' } })}
                        columns={[
                          { title: 'Id', dataIndex: 'id' },
                          { title: 'Typology', dataIndex: 'kind', render: (v) => <PatternTag pattern={v} /> },
                          { title: 'Accounts', dataIndex: 'accounts', render: (v: string[]) => v.join(', ') },
                          { title: 'Transfers', render: (_, x) => x.tx_ids.length, align: 'right' },
                          { title: 'Basis', dataIndex: 'reason' },
                        ]}
                      />
                    ),
                  },
                  { key: 'timeline', label: 'Audit trail', children: <AuditTab caseId={c.case_id} /> },
                ]}
              />
            </Card>
          </Col>

          <Col xs={24} xl={9}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <AssessmentCard c={c} />
              <DecisionCard c={c} />
            </Space>
          </Col>
        </Row>
      </Space>
    </div>
  )
}

function AssessmentCard({ c }: { c: CaseDetail }) {
  const d = c.draft
  const hyp = c.analysis?.hypothesis
  return (
    <Card size="small" title={<span className="panel-title">AI assessment (advisory)</span>}>
      {!d ? (
        <Empty description={LIVE.has(c.status) ? 'Automated review in progress' : 'No assessment'} />
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space wrap>
            <span>Typology</span>
            <PatternTag pattern={d.pattern_hypothesis} />
            <span>Recommendation</span>
            <ActionTag action={d.recommended_action} />
            <span>Confidence</span>
            <Tag>{d.confidence}</Tag>
          </Space>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{d.summary}</Typography.Paragraph>
          {hyp?.rationale && (
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              <b>Rationale:</b> {hyp.rationale}
            </Typography.Paragraph>
          )}
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            <b>Limitations:</b> {d.limitations}
          </Typography.Paragraph>
          <Space>
            <VerifiedBadge faithful={c.verification?.faithful} />
            <span>
              {c.verification
                ? c.verification.faithful
                  ? `Supporting transactions verified against source data (${c.verification.evidence_rows})`
                  : 'Verification of supporting transactions failed'
                : 'Not verified'}
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
          <Row gutter={8}>
            <Col span={8}>
              <Statistic title="AI reasoning steps" value={Number(c.metrics.steps ?? 0)} />
            </Col>
            <Col span={8}>
              <Statistic title="Data lookups" value={Number(c.metrics.tool_calls ?? 0)} />
            </Col>
            <Col span={8}>
              <Statistic
                title="Tokens"
                value={Number(c.metrics.input_tokens ?? 0) + Number(c.metrics.output_tokens ?? 0)}
              />
            </Col>
          </Row>
        </Space>
      )}
    </Card>
  )
}

function DecisionCard({ c }: { c: CaseDetail }) {
  const user = useUser()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [action, setAction] = useState<Decision['action']>('approve')
  const [reason, setReason] = useState('')
  const decide = useMutation({
    mutationFn: () => api.decide(c.case_id, action, reason, user.name),
    onSuccess: () => {
      message.success('Decision recorded')
      setReason('')
      queryClient.invalidateQueries({ queryKey: ['case', c.case_id] })
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
    onError: (e) => message.error(String(e)),
  })

  const escalation = action === 'approve' && c.draft?.recommended_action === 'escalate'
  const needsSupervisor = escalation && user.role !== 'supervisor'
  const canDecide = c.status === 'pending_review'

  return (
    <Card size="small" title={<span className="panel-title">Analyst decision</span>}>
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
            <Radio.Group
              value={action}
              onChange={(e) => setAction(e.target.value)}
              optionType="button"
              options={[
                { value: 'approve', label: DECISION_LABEL.approve },
                { value: 'reject', label: DECISION_LABEL.reject },
                { value: 'request_more', label: DECISION_LABEL.request_more },
              ]}
            />
            {escalation && (
              <Alert
                type={needsSupervisor ? 'warning' : 'info'}
                showIcon
                icon={<LockOutlined />}
                message="Four-eyes rule: accepting an escalation requires supervisor approval."
                description="Switch to the Supervisor role to accept an escalation."
              />
            )}
            <Input.TextArea
              rows={3}
              placeholder="Rationale for the decision (required, recorded in the audit trail)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button
              type="primary"
              block
              disabled={reason.trim().length < 3 || needsSupervisor}
              loading={decide.isPending}
              onClick={() => decide.mutate()}
            >
              Record decision as {user.name}
            </Button>
          </>
        ) : (
          <Typography.Text type="secondary">
            {LIVE.has(c.status)
              ? 'Automated review in progress.'
              : c.status === 'pending_review'
                ? ''
                : 'This case is closed. Recorded decisions cannot be changed.'}
          </Typography.Text>
        )}
      </Space>
    </Card>
  )
}

function AuditTab({ caseId }: { caseId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['audit', caseId],
    queryFn: () => api.audit(caseId),
    refetchInterval: 5000,
  })
  if (isLoading) return <Spin />
  if (!data) return <Empty />
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space>
        <Tag color={data.chain_valid ? 'green' : 'red'}>
          {data.chain_valid ? 'Hash chain intact' : 'Hash chain broken'}
        </Tag>
        <Typography.Text type="secondary">{data.events.length} events, append-only</Typography.Text>
      </Space>
      <div style={{ maxHeight: 520, overflow: 'auto', paddingTop: 8 }}>
        <Timeline
          items={data.events.map((e) => ({
            color:
              e.event_type === 'model_call'
                ? 'blue'
                : e.event_type === 'tool_call'
                  ? 'gray'
                  : e.event_type.startsWith('decision')
                    ? 'red'
                    : 'green',
            children: (
              <span style={{ fontSize: 12 }}>
                <b>{e.event_type}</b> <Tag>{e.actor}</Tag>
                <span className="mono">{describe(e)}</span>{' '}
                <Typography.Text type="secondary">{dayjs(e.created_at).format('HH:mm:ss')}</Typography.Text>
              </span>
            ),
          }))}
        />
      </div>
    </Space>
  )
}

function describe(e: { event_type: string; payload: Record<string, unknown> }) {
  const p = e.payload
  switch (e.event_type) {
    case 'tool_call':
      return `${p.name} ${p.ok ? 'ok' : 'error'} ${p.duration_ms} ms`
    case 'model_call':
      return `${p.model} in ${p.input_tokens} / out ${p.output_tokens} tokens`
    case 'node_started':
    case 'node_finished':
    case 'node_interrupted':
      return String(p.node)
    case 'decision_recorded':
    case 'decision_applied':
      return `${p.action} by ${p.reviewer}`
    case 'status':
      return String(p.status)
    default:
      return ''
  }
}
