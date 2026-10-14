import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert as AntAlert, App, Button, Card, Space, Table, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { api, type Alert } from '../api'

export default function AlertInbox() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const { data, isLoading, error } = useQuery({ queryKey: ['alerts', 'dev'], queryFn: () => api.alerts('dev') })
  const open = useMutation({
    mutationFn: (alertId: string) => api.openCase(alertId),
    onSuccess: (res) => {
      message.success(`Case ${res.case_id} opened; the AI investigation has started`)
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      navigate(`/cases/${res.case_id}`)
    },
    onError: (e) => message.error(String(e)),
  })

  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Alert inbox
        </Typography.Title>
        <AntAlert
          type="info"
          showIcon
          message="Alerts here come from the development alert set (one seed account and a time window each). Rules-based detection with risk scores will replace this source."
        />
        {error && <AntAlert type="error" showIcon message={String(error)} />}
        <Card size="small" styles={{ body: { padding: 0 } }}>
          <Table<Alert>
            size="small"
            rowKey="alert_id"
            loading={isLoading}
            dataSource={data ?? []}
            pagination={{ pageSize: 25, showSizeChanger: false }}
            columns={[
              { title: 'Alert', dataIndex: 'alert_id', render: (v) => <span className="mono">{v}</span> },
              {
                title: 'Subject account',
                render: (_, a) => (
                  <span className="mono">
                    {a.seed_bank}/{a.seed_account}
                  </span>
                ),
              },
              {
                title: 'Window',
                render: (_, a) =>
                  `${dayjs(a.window_start).format('MM-DD HH:mm')} to ${dayjs(a.window_end).format('MM-DD HH:mm')}`,
              },
              {
                title: 'Case',
                dataIndex: 'case_id',
                render: (v: string | null, a) =>
                  v ? (
                    <Button size="small" type="link" onClick={() => navigate(`/cases/${v}`)}>
                      {v}
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      loading={open.isPending && open.variables === a.alert_id}
                      onClick={() => open.mutate(a.alert_id)}
                    >
                      Open case
                    </Button>
                  ),
              },
            ]}
          />
        </Card>
      </Space>
    </div>
  )
}
