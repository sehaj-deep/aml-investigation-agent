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
        acc[key] ??= { key, model: c.model, prompt: c.prompt_version ?? 'n/a', cases: 0 }
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
          Model governance
        </Typography.Title>
        <Card size="small" title={<span className="panel-title">Models and prompt versions in use</span>}>
          <Table
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={inventory}
            columns={[
              { title: 'Model', dataIndex: 'model', render: (v) => <span className="mono">{v}</span> },
              { title: 'Prompt version', dataIndex: 'prompt', render: (v) => <Tag>{v}</Tag> },
              { title: 'Cases', dataIndex: 'cases', align: 'right' },
            ]}
          />
        </Card>
        <Card size="small" title={<span className="panel-title">Controls in force</span>}>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="Data access">
              The AI reaches data only through read-only, bounded tools; it never sees labels.
            </Descriptions.Item>
            <Descriptions.Item label="Evidence">
              Supporting transactions are collected by the system from the accounts the AI identifies,
              and each one is verified against the source data before review.
            </Descriptions.Item>
            <Descriptions.Item label="Human approval">
              No case is closed without a recorded analyst decision; escalations require supervisor approval.
            </Descriptions.Item>
            <Descriptions.Item label="Audit">
              Append-only, hash-chained log of every model call, tool call and decision.
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
