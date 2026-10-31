import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { api, type CaseGraph as Graph, type GraphNodeDetail } from '../../api'
import { Details } from '../EntityGraph'
import { label } from '../../ui'

const COLUMN = 205
const ROW = 66
const COLUMNS: Record<string, number> = {
  customer: 0, account: 1, application: 1, policy: 1, transaction: 2, claim: 2, device: 3, ip: 3, phone: 3, beneficiary: 4,
}
const COLOURS: Record<string, string> = {
  customer: '#0f766e', account: '#0f172a', application: '#0369a1', policy: '#b45309', claim: '#c2410c',
  transaction: '#475569', device: '#2563eb', ip: '#4f46e5', phone: '#0891b2', beneficiary: '#7c3aed',
}
const LINK = '#dc2626'

type EntityData = Record<string, unknown> & { title: string; subtitle: string; kind: string; link: boolean; faded: boolean; selected: boolean }

function EntityNode({ data }: NodeProps<Node<EntityData>>) {
  const colour = data.link ? LINK : COLOURS[data.kind]
  return (
    <div
      className={`w-36 rounded-lg border-2 bg-white px-2.5 py-1.5 shadow-sm transition-opacity ${data.selected ? 'ring-2 ring-offset-1' : ''}`}
      style={{ borderColor: colour, opacity: data.faded ? 0.25 : 1, ['--tw-ring-color' as string]: colour }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div className="truncate text-sm font-medium text-slate-900">{data.title}</div>
      <div className="truncate text-xs text-slate-500">{data.subtitle}</div>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  )
}

const NODE_TYPES = { entity: EntityNode }

function positions(graph: Graph) {
  const columns = new Map<number, string[]>()
  for (const node of graph.nodes) {
    const column = COLUMNS[node.type] ?? 4
    columns.set(column, [...(columns.get(column) ?? []), node.id])
  }
  const placed = new Map<string, { x: number; y: number }>()
  for (const [column, ids] of columns) {
    ids.forEach((id, i) => placed.set(id, { x: column * COLUMN, y: (i - (ids.length - 1) / 2) * ROW }))
  }
  return placed
}

export default function CaseGraph({ graph, linkIds }: { graph: Graph; linkIds: Set<string> }) {
  const [picked, setPicked] = useState<string | null>(null)
  const [detail, setDetail] = useState<GraphNodeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const kinds = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n.type])), [graph])

  useEffect(() => {
    if (!picked) return
    let current = true
    setDetail(null)
    setError(null)
    api.graphNode(picked, kinds.get(picked) ?? 'account')
      .then((d) => { if (current) setDetail(d) })
      .catch((e) => { if (current) setError(e.message) })
    return () => { current = false }
  }, [picked, kinds])

  const { nodes, edges, near } = useMemo(() => {
    const placed = positions(graph)
    const close = new Set(picked ? [picked] : [])
    for (const e of graph.edges) {
      if (e.source === picked) close.add(e.target)
      if (e.target === picked) close.add(e.source)
    }
    const nodes: Node[] = graph.nodes.map((n) => ({
      id: n.id,
      type: 'entity',
      position: placed.get(n.id)!,
      data: {
        title: n.label,
        subtitle: n.type === 'ip' ? 'IP address' : n.label === n.id ? label(n.type) : `${label(n.type)} ${n.id}`,
        kind: n.type,
        link: linkIds.has(n.id),
        faded: Boolean(picked) && !close.has(n.id),
        selected: n.id === picked,
      },
    }))
    const edges: Edge[] = graph.edges.map((e) => {
      const hot = linkIds.has(e.target) || linkIds.has(e.source)
      const faded = Boolean(picked) && !(close.has(e.source) && close.has(e.target))
      const colour = hot ? LINK : '#94a3b8'
      // Lines run left to right whichever way the relationship reads.
      const flipped = (COLUMNS[kinds.get(e.source) ?? ''] ?? 4) > (COLUMNS[kinds.get(e.target) ?? ''] ?? 4)
      return {
        id: `${e.source}-${e.target}-${e.label}`,
        source: flipped ? e.target : e.source,
        target: flipped ? e.source : e.target,
        label: picked && !faded ? e.label : undefined, // twenty labels at once are unreadable
        style: { stroke: colour, strokeWidth: hot ? 2 : 1.25, opacity: faded ? 0.12 : 1 },
        labelStyle: { fontSize: 10, fill: '#64748b', opacity: faded ? 0.12 : 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: colour },
      }
    })
    return { nodes, edges, near: graph.edges.filter((e) => e.source === picked || e.target === picked) }
  }, [graph, kinds, linkIds, picked])

  return (
    <div className="space-y-2">
      <div className="grid gap-3 lg:grid-cols-[1fr_16rem]">
        <div className="h-[36rem] overflow-hidden rounded-md border border-slate-200 bg-slate-50 text-slate-900">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.04, maxZoom: 1 }}
            minZoom={0.15}
            maxZoom={2}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => setPicked(node.id)}
            onPaneClick={() => setPicked(null)}
          >
            <Background gap={20} color="#e2e8f0" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <aside className="max-h-[36rem] space-y-3 overflow-y-auto rounded-md border border-slate-200 p-3">
          <Details detail={picked ? detail : null} error={picked ? error : null} isFocus />
          {picked && near.length > 0 && (
            <div className="text-sm">
              <h3 className="text-xs font-semibold text-slate-500">Why it's connected</h3>
              <ul className="mt-1 space-y-1 text-xs">
                {near.map((e) => (
                  <li key={`${e.source}-${e.target}-${e.label}`}>
                    {e.source} {e.label} {e.target}
                    <span className="block text-slate-500">Source: {e.evidence}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
      <p className="text-xs text-slate-600">
        Every line comes from a matching identifier in a source record, never from the AI model.
        <span className="ml-1" style={{ color: LINK }}>Red marks the identifiers that grouped these Alerts.</span>
        {graph.out_of_scope_count > 0 && <span className="ml-1">{graph.out_of_scope_count} linked account(s) sit outside your Portfolio.</span>}
      </p>
    </div>
  )
}
