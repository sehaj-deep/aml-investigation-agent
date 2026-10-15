import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Space, Table, Tag, Typography } from 'antd'
import { api } from '../api'

// Model inventory derived from the cases themselves, plus the controls in force.
export default function Governance() {
  const { data } = useQuery({ queryKey: ['cases'], queryFn: api.cases })
  const inventory = Object.values(
    (data ?? []).reduce<Record<string, { key: string; model: string; prompt: string; cases: number }>>(
      (acc, c) => {
        if (!c.model) return acc
        const key = `${c.model}|${c.prompt_version}`
        const version = c.prompt_version ? `Version ${c.prompt_version.replace(/^p/, '')}` : 'n/a'
        acc[key] ??= { key, model: c.model, prompt: version, cases: 0 }
        acc[key].cases += 1
        return acc
      },
      {},
    ),
  )
  return (
    <div className="page">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Governance
        </Typography.Title>
        <Card size="small" title={<span className="panel-title">Transaction monitoring model</span>}>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="Model">
              Gradient-boosted trees (XGBoost, open source) scoring every payment from the payment
              itself and the behavior of both accounts.
            </Descriptions.Item>
            <Descriptions.Item label="Alert policy">
              Set to catch 84% of laundering accounts in the validation period, at about 93% false
              alarms (typical for banks). Priority (high, medium, low) only orders the work.
            </Descriptions.Item>
            <Descriptions.Item label="Below-the-line testing">
              A random sample of 250 accounts scored just under the threshold is reviewed like alerts,
              to measure how much laundering the threshold misses.
            </Descriptions.Item>
            <Descriptions.Item label="Explanations">
              Each alert shows the main reasons behind its score.
            </Descriptions.Item>
          </Descriptions>
        </Card>
        <Card size="small" title={<span className="panel-title">AI review: models and instruction versions in use</span>}>
          <Table
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={inventory}
            columns={[
              { title: 'AI model', dataIndex: 'model', render: (v) => <span className="mono">{v}</span> },
              { title: 'Instructions', dataIndex: 'prompt', render: (v) => <Tag>{v}</Tag> },
              { title: 'Cases', dataIndex: 'cases', align: 'right' },
            ]}
          />
        </Card>
        <Card size="small" title={<span className="panel-title">Controls in force</span>}>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="Data access">
              The AI reads data only through read-only, limited lookups; it never sees the answers
              used to test it.
            </Descriptions.Item>
            <Descriptions.Item label="Evidence">
              Supporting transactions are collected by the system from the accounts the AI identifies,
              and each one is verified against the source data before review.
            </Descriptions.Item>
            <Descriptions.Item label="Human approval">
              No case is closed without a recorded analyst decision. Every escalation must be confirmed by a
              supervisor other than the person who escalated it, and the server refuses anything else.
            </Descriptions.Item>
            <Descriptions.Item label="Audit">
              Every AI step, data lookup and decision is recorded in a log that cannot be edited
              and is checked for tampering.
            </Descriptions.Item>
            <Descriptions.Item label="Data">
              Synthetic transactions (IBM AMLworld HI-Small); results do not show real-world performance.
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Space>
    </div>
  )
}
