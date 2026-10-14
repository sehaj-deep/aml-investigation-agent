import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Col, Progress, Row, Space, Statistic, Typography } from 'antd'
import { api } from '../api'
import { RECOMMENDATION, typologyName } from '../terms'
import { statusText } from '../components/badges'

function Breakdown({
  title,
  data,
  label = (k) => k,
}: {
  title: string
  data: Record<string, number>
  label?: (key: string) => string
}) {
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1])
  return (
    <Card size="small" title={<span className="panel-title">{title}</span>}>
      {rows.length === 0 && <Typography.Text type="secondary">No data yet</Typography.Text>}
      {rows.map(([k, v]) => (
        <div key={k} style={{ marginBottom: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
            <span>{label(k)}</span>
            <span>{v}</span>
          </div>
          <Progress percent={Math.round((100 * v) / total)} showInfo={false} size="small" />
        </div>
      ))}
    </Card>
  )
}

export default function Dashboard() {
  const { data, error } = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 10000 })
  const s = data
  const total = s ? Object.values(s.by_status).reduce((a, b) => a + b, 0) : 0
  const open = s
    ? total - (s.by_status.approved ?? 0) - (s.by_status.rejected ?? 0)
    : 0
  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Operations
        </Typography.Title>
        {error && <Alert type="error" showIcon message={String(error)} />}
        <Row gutter={12}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="Cases" value={total} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="Open" value={open} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="Pending analyst review" value={s?.by_status.pending_review ?? 0} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="Cases with verified support"
                value={s ? s.verification.faithful : 0}
                suffix={`/ ${s?.verification.checked ?? 0}`}
              />
            </Card>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            <Breakdown title="Cases by status" data={s?.by_status ?? {}} label={statusText} />
          </Col>
          <Col span={8}>
            <Breakdown
              title="AI recommendation"
              data={s?.by_recommended_action ?? {}}
              label={(k) => RECOMMENDATION[k]?.name ?? k}
            />
          </Col>
          <Col span={8}>
            <Breakdown title="Typology (AI)" data={s?.by_pattern ?? {}} label={typologyName} />
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            <Breakdown
              title="Analyst decisions"
              data={s?.decisions ?? {}}
              label={(k) => ({ approve: 'Accepted', reject: 'Overridden', request_more: 'Returned' })[k] ?? k}
            />
          </Col>
        </Row>
      </Space>
    </div>
  )
}
