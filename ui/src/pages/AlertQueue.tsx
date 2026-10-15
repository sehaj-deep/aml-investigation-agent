import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { Alert, App, Card, Input, Select, Space, Table, Tooltip, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { api, type QueueAlert, type WorkStatus } from '../api'
import { ActionTag, PriorityTag, StatusTag } from '../components/badges'
import { factorText } from '../terms'

const PAGE = 50

const STATUS_FILTERS: { label: string; value: string }[] = [
  { label: 'All open alerts', value: 'open' },
  { label: 'New', value: 'new' },
  { label: 'Ready for review', value: 'pending_review' },
  { label: 'AI review in progress', value: 'running' },
  { label: 'Awaiting supervisor approval', value: 'pending_approval' },
  { label: 'Closed: false alarm', value: 'closed' },
  { label: 'Escalated for SAR review', value: 'escalated' },
  { label: 'All alerts', value: '' },
]

const PRIORITY_FILTERS = [
  { label: 'All priorities', value: '' },
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
  { label: 'Below-the-line sample', value: 'sample' },
]

function reasons(a: QueueAlert) {
  const r = (a.reasons ?? []).map(factorText)
  return r.length ? r.join('; ') : ''
}

export default function AlertQueue() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [status, setStatus] = useState('open')
  const [priority, setPriority] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['alerts', status, priority, search, page],
    queryFn: () =>
      api.alerts({ status, priority, q: search, limit: PAGE, offset: (page - 1) * PAGE }),
    placeholderData: keepPreviousData,
    refetchInterval: 5000,
  })
  const open = useMutation({
    mutationFn: (alertId: string) => api.openAlert(alertId),
    onSuccess: (res) => navigate(`/cases/${res.case_id}`),
    onError: (e) => message.error(String(e)),
  })

  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v)
    setPage(1)
  }

  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Alert queue
        </Typography.Title>
        <Typography.Text type="secondary">
          Alerts raised by transaction monitoring, highest risk first, then a below-the-line
          sample of accounts scored just under the threshold. As in any bank, most alerts are
          false alarms. Open an alert to start its AI review.
        </Typography.Text>
        {error && <Alert type="error" showIcon message={`Could not load alerts: ${String(error)}`} />}
        <Card size="small">
          <Space wrap>
            <Select value={status} onChange={reset(setStatus)} options={STATUS_FILTERS} style={{ width: 200 }} />
            <Select
              value={priority}
              onChange={reset(setPriority)}
              options={PRIORITY_FILTERS}
              style={{ width: 150 }}
            />
            <Input.Search
              allowClear
              placeholder="Alert, case or account"
              onSearch={reset(setSearch)}
              style={{ width: 260 }}
            />
            <Typography.Text type="secondary">
              {data ? `${data.total.toLocaleString()} alerts` : ''}
            </Typography.Text>
          </Space>
        </Card>
        <Table<QueueAlert>
          size="small"
          rowKey="alert_id"
          loading={isLoading || isFetching || open.isPending}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize: PAGE,
            total: data?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
          onRow={(a) => ({ onClick: () => open.mutate(a.alert_id), style: { cursor: 'pointer' } })}
          columns={[
            {
              title: 'Priority',
              dataIndex: 'priority',
              render: (_, a) => <PriorityTag priority={a.priority} score={a.score} />,
            },
            { title: 'Alert', dataIndex: 'alert_id', render: (v: string) => <span className="mono">{v}</span> },
            {
              title: 'Account',
              render: (_, a) => (
                <span className="mono">
                  {a.seed_bank}/{a.seed_account}
                </span>
              ),
            },
            {
              title: 'Why flagged',
              render: (_, a) => (
                <Tooltip title={reasons(a)}>
                  <Typography.Text ellipsis style={{ maxWidth: 320, display: 'inline-block' }}>
                    {reasons(a)}
                  </Typography.Text>
                </Tooltip>
              ),
            },
            { title: 'Flagged payments', dataIndex: 'n_triggers', align: 'right' },
            {
              title: 'Review period',
              render: (_, a) =>
                `${dayjs(a.window_start).format('MMM D HH:mm')} to ${dayjs(a.window_end).format('MMM D HH:mm')}`,
            },
            { title: 'Status', dataIndex: 'status', render: (v: WorkStatus) => <StatusTag status={v} /> },
            {
              title: 'AI recommendation',
              dataIndex: 'recommended_action',
              render: (v, a) => (a.status === 'new' ? '' : <ActionTag action={v} />),
            },
          ]}
        />
      </Space>
    </div>
  )
}
