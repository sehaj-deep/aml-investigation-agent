import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Input, Select, Space, Table, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { api, type CaseRow, type CaseStatus } from '../api'
import { ActionTag, PatternTag, StatusTag, VerifiedBadge } from '../components/badges'

const STATUS_FILTERS: { label: string; value: CaseStatus | 'all' | 'open' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Open cases', value: 'open' },
  { label: 'Pending analyst review', value: 'pending_review' },
  { label: 'Automated review in progress', value: 'running' },
  { label: 'New', value: 'queued' },
  { label: 'Closed: AI accepted', value: 'approved' },
  { label: 'Closed: AI overridden', value: 'rejected' },
  { label: 'Processing error', value: 'failed' },
]

export default function CaseQueue() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<CaseStatus | 'all' | 'open'>('open')
  const [search, setSearch] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['cases'],
    queryFn: api.cases,
    refetchInterval: 5000,
  })

  const rows = useMemo(() => {
    const all = data ?? []
    return all
      .filter((c) =>
        status === 'all'
          ? true
          : status === 'open'
            ? !['approved', 'rejected'].includes(c.status)
            : c.status === status,
      )
      .filter((c) =>
        search
          ? `${c.case_id} ${c.alert_id} ${c.seed_bank}/${c.seed_account}`
              .toLowerCase()
              .includes(search.toLowerCase())
          : true,
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
  }, [data, status, search])

  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Case queue
        </Typography.Title>
        {error && <Alert type="error" showIcon message={`Could not load cases: ${String(error)}`} />}
        <Card size="small">
          <Space wrap>
            <Select
              value={status}
              onChange={setStatus}
              options={STATUS_FILTERS}
              style={{ width: 200 }}
            />
            <Input.Search
              allowClear
              placeholder="Case, alert or subject account"
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 280 }}
            />
            <Typography.Text type="secondary">{rows.length} cases</Typography.Text>
          </Space>
        </Card>
        <Table<CaseRow>
          size="small"
          rowKey="case_id"
          loading={isLoading}
          dataSource={rows}
          pagination={{ pageSize: 25, showSizeChanger: false }}
          onRow={(r) => ({ onClick: () => navigate(`/cases/${r.case_id}`), style: { cursor: 'pointer' } })}
          columns={[
            {
              title: 'Case',
              dataIndex: 'case_id',
              render: (v: string) => <span className="mono">{v}</span>,
            },
            { title: 'Alert', dataIndex: 'alert_id', render: (v: string) => <span className="mono">{v}</span> },
            {
              title: 'Subject account',
              render: (_, r) => (
                <span className="mono">
                  {r.seed_bank}/{r.seed_account}
                </span>
              ),
            },
            { title: 'Status', dataIndex: 'status', render: (v: CaseStatus) => <StatusTag status={v} /> },
            { title: 'Typology (AI)', dataIndex: 'pattern', render: (v) => <PatternTag pattern={v} /> },
            {
              title: 'AI recommendation',
              dataIndex: 'recommended_action',
              render: (v) => <ActionTag action={v} />,
            },
            { title: 'Confidence', dataIndex: 'confidence', render: (v) => v ?? '' },
            { title: 'Supporting txns', dataIndex: 'n_evidence', align: 'right' },
            {
              title: 'Verified',
              dataIndex: 'faithful',
              align: 'center',
              render: (v) => <VerifiedBadge faithful={v} />,
            },
            { title: 'Warnings', dataIndex: 'n_warnings', align: 'right' },
            {
              title: 'Opened',
              dataIndex: 'created_at',
              render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
              sorter: (a, b) => a.created_at.localeCompare(b.created_at),
            },
          ]}
        />
      </Space>
    </div>
  )
}
