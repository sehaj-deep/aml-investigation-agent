import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Drawer, Empty, Input, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import { CheckCircleFilled, LoadingOutlined, MessageOutlined } from '@ant-design/icons'
import { api, type CopilotAnswer, type CopilotEvent } from '../api'

const SUGGESTIONS = [
  'Has the subject dealt with these counterparties before?',
  'Where did the money go after the flagged payments?',
  'Is the main counterparty a regular hub or a new account?',
  'Summarize this case in three sentences.',
]

function AnswerBlock({ a, onCite }: { a: CopilotAnswer; onCite: (ids: number[]) => void }) {
  const verified = a.cited.filter((t) => !a.unverified.includes(t))
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="copilot-q">{a.question}</div>
      <div className="copilot-a">
        <Typography.Paragraph style={{ marginBottom: 6, whiteSpace: 'pre-wrap' }}>{a.answer}</Typography.Paragraph>
        {a.tools.length > 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
            Checked: {a.tools.map((t) => t.text).join('; ')}
          </Typography.Text>
        )}
        {a.cited.length > 0 && (
          <Space size={4} wrap style={{ marginTop: 6 }}>
            {verified.length > 0 && (
              <Button size="small" type="link" style={{ padding: 0 }} onClick={() => onCite(verified)}>
                Show cited transactions in the network
              </Button>
            )}
            {verified.map((t) => (
              <Tag key={t} icon={<CheckCircleFilled />} color="green" className="mono">
                tx {t}
              </Tag>
            ))}
            {a.unverified.map((t) => (
              <Tooltip key={t} title="This transaction was not returned by any data lookup in this case. Do not rely on it.">
                <Tag color="red" className="mono">
                  tx {t}: not found
                </Tag>
              </Tooltip>
            ))}
          </Space>
        )}
      </div>
    </div>
  )
}

export default function CopilotPanel({
  caseId,
  ready,
  onCite,
}: {
  caseId: string
  ready: boolean
  onCite: (ids: number[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState<string | null>(null)
  const [steps, setSteps] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const bottom = useRef<HTMLDivElement>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['copilot', caseId],
    queryFn: () => api.copilotHistory(caseId),
    enabled: open,
  })

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [data, steps, asking])

  const ask = async (q: string) => {
    if (!q.trim() || asking) return
    setAsking(q)
    setSteps([])
    setError(null)
    setQuestion('')
    try {
      await api.askCopilot(caseId, q, (e: CopilotEvent) => {
        if (e.type === 'tool') setSteps((s) => [...s, e.text])
        if (e.type === 'error') setError(e.message)
      })
    } catch (e) {
      setError(String(e))
    } finally {
      setAsking(null)
      queryClient.invalidateQueries({ queryKey: ['copilot', caseId] })
      queryClient.invalidateQueries({ queryKey: ['audit', caseId] })
    }
  }

  const history = data?.answers ?? []
  return (
    <>
      <Button icon={<MessageOutlined />} onClick={() => setOpen(true)} disabled={!ready}>
        Ask the copilot
      </Button>
      <Drawer
        title="Investigator copilot"
        open={open}
        onClose={() => setOpen(false)}
        width={460}
        mask={false}
        styles={{ body: { display: 'flex', flexDirection: 'column', padding: 12 } }}
      >
        <Typography.Text type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
          Ask about this case. The copilot reads the same data as the AI review, checks every
          transaction it cites, and cannot change the case. It advises; you decide.
        </Typography.Text>
        <div style={{ flex: 1, overflow: 'auto', paddingRight: 4 }}>
          {isLoading && <Spin />}
          {!isLoading && history.length === 0 && !asking && (
            <Empty description="No questions yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          {history.map((a) => (
            <AnswerBlock key={a.id} a={a} onCite={onCite} />
          ))}
          {asking && (
            <div style={{ marginBottom: 16 }}>
              <div className="copilot-q">{asking}</div>
              <div className="copilot-a">
                <Space direction="vertical" size={2}>
                  {steps.map((s, i) => (
                    <Typography.Text key={i} type="secondary" style={{ fontSize: 12 }}>
                      {s}
                    </Typography.Text>
                  ))}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    <LoadingOutlined /> Working on it...
                  </Typography.Text>
                </Space>
              </div>
            </div>
          )}
          {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 8 }} />}
          <div ref={bottom} />
        </div>
        <Space size={4} wrap style={{ margin: '8px 0' }}>
          {SUGGESTIONS.map((s) => (
            <Tag key={s} style={{ cursor: 'pointer' }} onClick={() => ask(s)}>
              {s}
            </Tag>
          ))}
        </Space>
        <Input.TextArea
          rows={2}
          placeholder="Ask a question about this case"
          value={question}
          disabled={!!asking}
          onChange={(e) => setQuestion(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              ask(question)
            }
          }}
        />
        <Space style={{ marginTop: 8, justifyContent: 'space-between', width: '100%' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {data ? `${data.used} of ${data.limit} questions used` : ''}
          </Typography.Text>
          <Button type="primary" onClick={() => ask(question)} loading={!!asking} disabled={!question.trim()}>
            Ask
          </Button>
        </Space>
      </Drawer>
    </>
  )
}
