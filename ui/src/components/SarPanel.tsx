import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Descriptions, Empty, Input, Space, Spin, Table, Tag, Typography } from 'antd'
import { DownloadOutlined, FileTextOutlined, LockOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type CaseDetail } from '../api'
import { useUser } from '../user'

const TITLES: Record<string, string> = {
  introduction: 'Introduction',
  subjects: 'Subjects and relationships (who)',
  activity: 'Suspicious activity (what, when, where, how)',
  why_suspicious: 'Why the activity is suspicious',
  conclusion: 'Conclusion and actions taken',
}

export default function SarPanel({ c }: { c: CaseDetail }) {
  const user = useUser()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['sar', c.case_id],
    queryFn: () => api.sar(c.case_id),
    enabled: c.status === 'escalated',
  })
  const sar = data?.sar ?? null
  const [sections, setSections] = useState<Record<string, string>>({})
  useEffect(() => {
    if (sar) setSections(sar.sections)
  }, [sar])

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['sar', c.case_id] })
    queryClient.invalidateQueries({ queryKey: ['audit', c.case_id] })
  }
  const draft = useMutation({
    mutationFn: () => api.draftSar(c.case_id),
    onSuccess: () => (message.success('Draft ready: review and save it'), refresh()),
    onError: (e) => message.error(String(e)),
  })
  const save = useMutation({
    mutationFn: () => api.saveSar(c.case_id, sections, user.name, user.role),
    onSuccess: () => (message.success('Reviewed draft saved'), refresh()),
    onError: (e) => message.error(String(e)),
  })
  const approve = useMutation({
    mutationFn: () => api.approveSar(c.case_id, user.name, user.role),
    onSuccess: () => (message.success('Report approved for filing'), refresh()),
    onError: (e) => message.error(String(e)),
  })

  if (c.status !== 'escalated')
    return (
      <Empty description="A suspicious activity report draft becomes available once a supervisor confirms the escalation." />
    )
  if (isLoading) return <Spin />

  if (!sar)
    return (
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          The escalation is confirmed. The AI can draft the report narrative from the case facts:
          the subject, the review period, the supporting transactions with exact amounts, the
          red flags and the decision trail. Code builds those facts; the AI only writes the text,
          and every transaction and amount it writes is checked against them.
        </Typography.Paragraph>
        <Button type="primary" icon={<FileTextOutlined />} loading={draft.isPending} onClick={() => draft.mutate()}>
          Draft the SAR narrative with AI
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Sandbox: synthetic data. Nothing is filed with any authority.
        </Typography.Text>
      </Space>
    )

  const approved = sar.status === 'approved'
  const dirty = Object.keys(sar.sections).some((k) => sections[k] !== sar.sections[k])
  const approveBlocker = approved
    ? null
    : user.role !== 'supervisor'
      ? 'A supervisor approves the report (four-eyes rule). Switch to the Supervisor role to approve.'
      : sar.source !== 'analyst'
        ? 'An analyst must review and save the AI draft before it can be approved.'
        : sar.author === user.name
          ? 'The report must be approved by someone other than its last editor.'
          : dirty
            ? 'Save or discard your changes first.'
            : null
  const f = sar.facts

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space wrap>
        {approved ? (
          <Tag color="green" icon={<LockOutlined />}>
            Approved for filing by {sar.approved_by} ({dayjs(sar.approved_at).format('YYYY-MM-DD HH:mm')})
          </Tag>
        ) : (
          <Tag color="gold">
            Draft version {sar.version_no}, {sar.source === 'ai' ? 'written by the AI, not yet reviewed' : `saved by ${sar.author}`}
          </Tag>
        )}
        {f.filing_due && <Tag>Filing due {f.filing_due}</Tag>}
        <Button size="small" icon={<DownloadOutlined />} href={`/api/cases/${c.case_id}/sar/export`}>
          Download
        </Button>
        {!approved && (data?.ai_drafts ?? 0) < (data?.ai_limit ?? 0) && (
          <Button size="small" loading={draft.isPending} onClick={() => draft.mutate()}>
            Redraft with AI
          </Button>
        )}
      </Space>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Sandbox: synthetic data. Nothing is filed with any authority.
      </Typography.Text>

      {sar.warnings.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          message="Check these points before approval"
          description={
            <ul style={{ margin: 0, paddingInlineStart: 16 }}>
              {sar.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          }
        />
      ) : (
        <Alert type="success" showIcon message="Every transaction and amount in the text matches the evidence." />
      )}

      {(data?.sections ?? Object.keys(TITLES)).map((key) => (
        <div key={key}>
          <div className="panel-title" style={{ marginBottom: 4 }}>
            {TITLES[key] ?? key}
          </div>
          <Input.TextArea
            autoSize={{ minRows: 3, maxRows: 12 }}
            value={sections[key] ?? ''}
            readOnly={approved}
            onChange={(e) => setSections((s) => ({ ...s, [key]: e.target.value }))}
          />
        </div>
      ))}

      {!approved && (
        <Space wrap>
          <Button type="primary" disabled={!dirty && sar.source === 'analyst'} loading={save.isPending} onClick={() => save.mutate()}>
            Save reviewed draft as {user.name}
          </Button>
          {dirty && <Button onClick={() => setSections(sar.sections)}>Discard changes</Button>}
          <Button disabled={!!approveBlocker} loading={approve.isPending} onClick={() => approve.mutate()}>
            Approve for filing
          </Button>
          {approveBlocker && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {approveBlocker}
            </Typography.Text>
          )}
        </Space>
      )}

      <div className="panel-title">Transactions in the report (from the evidence)</div>
      <Table
        size="small"
        rowKey="tx_id"
        dataSource={f.transactions}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        columns={[
          { title: 'Time', dataIndex: 'timestamp', render: (v: string) => dayjs(v).format('MMM D HH:mm') },
          { title: 'From', dataIndex: 'from', render: (v: string) => <span className="mono">{v}</span> },
          { title: 'To', dataIndex: 'to', render: (v: string) => <span className="mono">{v}</span> },
          {
            title: 'Amount',
            align: 'right',
            render: (_, t) => <span className="mono">{`${t.amount} ${t.currency}`}</span>,
          },
          { title: 'Reference', dataIndex: 'tx_id', render: (v: number) => <span className="mono">tx {v}</span> },
        ]}
      />
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Sent by the subject">
          {Object.entries(f.totals.sent_by_subject).map(([cur, v]) => `${v} ${cur}`).join('; ') || 'none'}
        </Descriptions.Item>
        <Descriptions.Item label="Received by the subject">
          {Object.entries(f.totals.received_by_subject).map(([cur, v]) => `${v} ${cur}`).join('; ') || 'none'}
        </Descriptions.Item>
      </Descriptions>
    </Space>
  )
}
