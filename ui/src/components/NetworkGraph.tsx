import { useEffect, useRef, useState } from 'react'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { Descriptions, Empty, Space, Tag, Typography } from 'antd'
import type { CaseGraph, GraphEdge, GraphNode } from '../api'

interface Props {
  graph: CaseGraph | null
  evidenceTxIds: Set<number>
  highlight: Set<string>
}

const HOP_COLOR: Record<string, string> = {
  '0': '#c05621',
  '1': '#1d4e89',
  '2': '#7a8aa0',
  trace: '#6b46c1',
}

function shortAccount(n: GraphNode) {
  return `${n.label}\n${n.bank_id}/${n.account}`
}

export default function NetworkGraph({ graph, evidenceTxIds, highlight }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const [selected, setSelected] = useState<
    { kind: 'node'; node: GraphNode } | { kind: 'edge'; edge: GraphEdge } | null
  >(null)

  useEffect(() => {
    if (!ref.current || !graph) return
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((n) => ({
        data: {
          id: n.label,
          name: shortAccount(n),
          hop: String(n.hop),
          color: HOP_COLOR[String(n.hop)] ?? '#7a8aa0',
          size: n.label === 'A0' ? 46 : 30,
          raw: n,
        },
      })),
      ...graph.edges.map((e, i) => ({
        data: {
          id: `e${i}`,
          source: e.src,
          target: e.dst,
          width: Math.min(1 + Math.log2(e.n_tx + 1), 6),
          evidence: e.tx_ids.some((t) => evidenceTxIds.has(t)) ? 1 : 0,
          oneoff: e.n_tx <= 2 ? 1 : 0,
          raw: e,
        },
      })),
    ]
    const instance = cytoscape({
      container: ref.current,
      elements,
      wheelSensitivity: 0.2,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)',
            width: 'data(size)',
            height: 'data(size)',
            label: 'data(name)',
            'font-size': 9,
            'text-wrap': 'wrap',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            color: '#2d3748',
            'border-width': 1,
            'border-color': '#ffffff',
          },
        },
        {
          selector: 'node.hl',
          style: { 'border-width': 4, 'border-color': '#c53030' },
        },
        {
          selector: 'edge',
          style: {
            width: 'data(width)',
            'line-color': '#c3cddb',
            'target-arrow-color': '#c3cddb',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'arrow-scale': 0.8,
          },
        },
        {
          selector: 'edge[oneoff = 1]',
          style: { 'line-color': '#7f93ad', 'target-arrow-color': '#7f93ad', 'line-style': 'dashed' },
        },
        {
          selector: 'edge[evidence = 1]',
          style: {
            'line-color': '#c53030',
            'target-arrow-color': '#c53030',
            'line-style': 'solid',
            width: 3.5,
            'z-index': 10,
          },
        },
        { selector: ':selected', style: { 'overlay-opacity': 0.15, 'overlay-color': '#1d4e89' } },
      ],
      layout: {
        name: 'concentric',
        concentric: (n) => {
          const hop = n.data('hop')
          return hop === '0' ? 4 : hop === '1' ? 3 : hop === 'trace' ? 1 : 2
        },
        levelWidth: () => 1,
        minNodeSpacing: 18,
        animate: false,
      },
    })
    instance.on('tap', 'node', (evt) => setSelected({ kind: 'node', node: evt.target.data('raw') }))
    instance.on('tap', 'edge', (evt) => setSelected({ kind: 'edge', edge: evt.target.data('raw') }))
    instance.on('tap', (evt) => {
      if (evt.target === instance) setSelected(null)
    })
    cy.current = instance
    return () => {
      instance.destroy()
      cy.current = null
    }
  }, [graph, evidenceTxIds])

  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.nodes().removeClass('hl')
    highlight.forEach((label) => instance.getElementById(label).addClass('hl'))
  }, [highlight, graph, evidenceTxIds])

  if (!graph || graph.nodes.length === 0) return <Empty description="No network yet" />

  return (
    <div>
      <div ref={ref} className="network" />
      <Space size={12} wrap style={{ marginTop: 6, fontSize: 12 }}>
        <span><Tag color="#c05621">A0</Tag>seed</span>
        <span><Tag color="#1d4e89">1</Tag>direct counterparty</span>
        <span><Tag color="#7a8aa0">2</Tag>second step</span>
        <span><Tag color="#6b46c1">T</Tag>found by trace</span>
        <span>dashed: one-off relationship</span>
        <span style={{ color: '#c53030' }}>red: evidence</span>
        <span>red ring: highlighted accounts</span>
      </Space>
      {selected && (
        <Descriptions size="small" bordered column={2} style={{ marginTop: 8 }}>
          {selected.kind === 'node' ? (
            <>
              <Descriptions.Item label="Account">
                <Typography.Text className="mono">
                  {selected.node.label} = {selected.node.bank_id}/{selected.node.account}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Jurisdiction">{selected.node.jurisdiction ?? 'n/a'}</Descriptions.Item>
              <Descriptions.Item label="Paid by (distinct)">{selected.node.senders ?? 'n/a'}</Descriptions.Item>
              <Descriptions.Item label="Pays (distinct)">{selected.node.receivers ?? 'n/a'}</Descriptions.Item>
            </>
          ) : (
            <>
              <Descriptions.Item label="Flow">
                {selected.edge.src} to {selected.edge.dst}
              </Descriptions.Item>
              <Descriptions.Item label="Transfers">{selected.edge.n_tx}</Descriptions.Item>
              <Descriptions.Item label="Totals">
                {selected.edge.totals.map((t) => `${t.total} ${t.currency}`).join(', ')}
              </Descriptions.Item>
              <Descriptions.Item label="Period">
                {selected.edge.first === selected.edge.last
                  ? selected.edge.first
                  : `${selected.edge.first} to ${selected.edge.last}`}
              </Descriptions.Item>
            </>
          )}
        </Descriptions>
      )}
    </div>
  )
}
