import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { api, type Alert, type Graph, type GraphNodeDetail } from '../api'
import { Badge, Button, Card, ErrorNote, Risk, label } from '../ui'

const COLUMN = 300
const ROW = 92
const COLOURS: Record<string, string> = { account: '#0f172a', device: '#2563eb', beneficiary: '#7c3aed' }
const FLAGGED = '#dc2626'

type EntityData = Record<string, unknown> & {
  title: string
  subtitle: string
  kind: string
  flagged: boolean
  faded: boolean
  selected: boolean
  focus: boolean
}

function EntityNode({ data }: NodeProps<Node<EntityData>>) {
  const colour = data.flagged ? FLAGGED : COLOURS[data.kind]
  return (
    <div
      className={`w-52 rounded-lg border-2 bg-white px-3 py-2 shadow-sm transition-opacity ${data.selected ? 'ring-2 ring-offset-1' : ''}`}
      style={{ borderColor: colour, opacity: data.faded ? 0.25 : 1, ['--tw-ring-color' as string]: colour }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colour }} />
        <span className={`truncate text-sm text-slate-900 ${data.focus ? 'font-semibold' : 'font-medium'}`}>{data.title}</span>
      </div>
      <div className="mt-0.5 truncate text-xs text-slate-500">{data.subtitle}</div>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  )
}

const NODE_TYPES = { entity: EntityNode }

function flaggedIds(alert: Alert, account: string) {
  const ids = new Set<string>()
  if (account !== alert.account_id) return ids
  if (alert.device_id) ids.add(alert.device_id)
  for (const record of alert.supporting_records) {
    const beneficiary = record.data.beneficiary_id
    if (typeof beneficiary === 'string') ids.add(beneficiary)
  }
  return ids
}

/** Flagged and shared nodes by default, so the suspicious path stands out. */
function visibleGraph(graph: Graph, flagged: Set<string>, showAll: boolean) {
  const links = new Map<string, number>()
  for (const edge of graph.edges) links.set(edge.target, (links.get(edge.target) ?? 0) + 1)
  const [focus, ...others] = graph.nodes
  const hubs = others.filter((n) => n.type !== 'account')
  const matters = (id: string) => flagged.has(id) || (links.get(id) ?? 0) > 1
  const important = hubs.filter((n) => matters(n.id))
  const shown = showAll || important.length === 0 ? hubs : important
  const ids = new Set(shown.map((n) => n.id))
  const accounts = others.filter(
    (n) => n.type === 'account' && graph.edges.some((e) => e.source === n.id && ids.has(e.target)),
  )
  const rank = (id: string) => (flagged.has(id) ? 0 : 1)
  return {
    focus,
    hubs: [...shown].sort((a, b) => rank(a.id) - rank(b.id)),
    accounts,
    hidden: hubs.length - shown.length,
  }
}

function column(ids: string[], x: number) {
  const top = -((ids.length - 1) * ROW) / 2
  return ids.map((id, i) => [id, { x, y: top + i * ROW }] as const)
}

export function Details({
  detail,
  error,
  isFocus,
  onRecentre,
  onPick,
}: {
  detail: GraphNodeDetail | null
  error: string | null
  isFocus: boolean
  onRecentre?: (id: string) => void
  onPick?: (id: string) => void
}) {
  if (error) return <ErrorNote message={error} />
  if (!detail) return <p className="text-sm text-slate-600">Click a node to see its details.</p>
  return (
    <div className="space-y-3 text-sm">
      <div>
        <Badge>{label(detail.type)}</Badge>
        <p className="mt-1 font-semibold break-all">{detail.title}</p>
        {detail.title !== detail.id && <p className="text-xs text-slate-500">{detail.id}</p>}
      </div>
      <dl className="space-y-1">
        {detail.facts.map((fact) => (
          <div key={fact.label} className="flex justify-between gap-3">
            <dt className="text-slate-500">{fact.label}</dt>
            <dd className="text-right">{fact.value}</dd>
          </div>
        ))}
      </dl>
      {detail.type === 'account' && !isFocus && onRecentre && <Button onClick={() => onRecentre(detail.id)}>Re-centre here</Button>}
      {detail.cases.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500">Open Cases</h3>
          <ul className="mt-1 space-y-1">
            {detail.cases.slice(0, 5).map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2">
                <a className="text-blue-700 underline" href={`#/cases/${c.id}`}>{c.id}</a>
                <Risk level={c.risk_level} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {detail.accounts.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500">Accounts in your Portfolio</h3>
          <ul className="mt-1 flex flex-wrap gap-1">
            {detail.accounts.map((account) => (
              <li key={account}>
                {onPick
                  ? <button type="button" className="text-xs text-blue-700 underline" onClick={() => onPick(account)}>{account}</button>
                  : <span className="text-xs">{account}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {detail.out_of_scope_count > 0 && (
        <p className="text-xs text-slate-500">{detail.out_of_scope_count} more outside your Portfolio</p>
      )}
      {detail.records && detail.records.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500">Associated records</h3>
          {detail.records.map((r) => (
            <details key={r.kind + r.source_ref} className="border-t border-slate-100 py-1 text-xs">
              <summary className="cursor-pointer">{label(r.kind)} {r.source_ref}</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2">{JSON.stringify(r.data, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}

export default function EntityGraph({ alert }: { alert: Alert }) {
  const [account, setAccount] = useState(alert.account_id)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [full, setFull] = useState(false)
  const [picked, setPicked] = useState<string | null>(null)
  const [detail, setDetail] = useState<GraphNodeDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    api.graph(account)
      .then((g) => {
        if (!current) return
        setGraph(g)
        setError(null)
      })
      .catch((e) => {
        if (current) setError(e.message)
      })
    return () => {
      current = false
    }
  }, [account])

  const flagged = useMemo(() => flaggedIds(alert, account), [alert, account])
  const view = useMemo(() => (graph ? visibleGraph(graph, flagged, showAll) : null), [graph, flagged, showAll])
  const kinds = useMemo(() => new Map(graph?.nodes.map((n) => [n.id, n.type])), [graph])

  useEffect(() => {
    if (!picked) return
    let current = true
    api.graphNode(picked, kinds.get(picked) ?? 'account')
      .then((d) => {
        if (!current) return
        setDetail(d)
        setDetailError(null)
      })
      .catch((e) => {
        if (current) setDetailError(e.message)
      })
    return () => {
      current = false
    }
  }, [picked, kinds])

  useEffect(() => {
    if (!full) return
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFull(false)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [full])

  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    if (!graph || !view) return { nodes: [], edges: [] }
    const positions = new Map([
      [view.focus.id, { x: 0, y: 0 }],
      ...column(view.hubs.map((n) => n.id), COLUMN),
      ...column(view.accounts.map((n) => n.id), COLUMN * 2),
    ])
    const shownEdges = graph.edges.filter((e) => positions.has(e.source) && positions.has(e.target))
    const near = new Set([picked ?? ''])
    for (const e of shownEdges) {
      if (e.source === picked) near.add(e.target)
      if (e.target === picked) near.add(e.source)
    }
    const all = [view.focus, ...view.hubs, ...view.accounts]
    return {
      nodes: all.map((n) => ({
        id: n.id,
        type: 'entity',
        position: { ...positions.get(n.id)! },
        data: {
          title: n.label,
          subtitle: n.label === n.id ? label(n.type) : n.id,
          kind: n.type,
          flagged: flagged.has(n.id),
          faded: Boolean(picked) && !near.has(n.id),
          selected: n.id === picked,
          focus: n.id === view.focus.id,
        },
      })),
      edges: shownEdges.map((e) => {
        // Accounts on the right point back at the shared node, so lines flow left to right.
        const reversed = e.source !== view.focus.id
        const hot = flagged.has(e.target)
        const faded = Boolean(picked) && !(near.has(e.source) && near.has(e.target))
        const colour = hot ? FLAGGED : '#94a3b8'
        return {
          id: `${e.source}-${e.target}-${e.label}`,
          source: reversed ? e.target : e.source,
          target: reversed ? e.source : e.target,
          label: e.label,
          animated: hot,
          style: { stroke: colour, strokeWidth: hot ? 2.5 : 1.5, opacity: faded ? 0.15 : 1 },
          labelStyle: { fontSize: 10, fill: '#64748b', opacity: faded ? 0.15 : 1 },
          markerEnd: { type: MarkerType.ArrowClosed, color: colour },
        }
      }),
    }
  }, [graph, view, flagged, picked])

  function recentre(id: string) {
    setAccount(id)
    setPicked(null)
    setShowAll(false)
  }

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      {account !== alert.account_id && <Button onClick={() => recentre(alert.account_id)}>Back to {alert.account_id}</Button>}
      {view && (view.hidden > 0 || showAll) && (
        <Button onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'Show what matters' : `Show all (${view.hidden} routine hidden)`}
        </Button>
      )}
      <Button onClick={() => setFull((v) => !v)}>{full ? 'Exit full screen' : 'Full screen'}</Button>
    </div>
  )

  const body = (
    <div className={`grid gap-4 lg:grid-cols-[1fr_16rem] ${full ? 'min-h-0 flex-1' : ''}`}>
      <div className={`overflow-hidden rounded-md border border-slate-200 bg-slate-50 text-slate-900 ${full ? 'h-full' : 'h-[26rem]'}`}>
        {nodes.length > 0 && (
          <ReactFlow
            key={`${account}-${showAll}-${full}`}
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.15, maxZoom: 1.1 }}
            minZoom={0.2}
            maxZoom={2}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => setPicked(node.id)}
            onPaneClick={() => setPicked(null)}
            onNodeDoubleClick={(_, node) => {
              if (kinds.get(node.id) === 'account' && node.id !== account) recentre(node.id)
            }}
          >
            <Background gap={20} color="#e2e8f0" />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
      <aside className="overflow-y-auto rounded-md border border-slate-200 p-3">
        <Details
          detail={picked ? detail : null}
          error={picked ? detailError : null}
          isFocus={detail?.id === account}
          onRecentre={recentre}
          onPick={recentre}
        />
      </aside>
    </div>
  )

  const legend = (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      <span style={{ color: COLOURS.account }}>● Account</span>
      <span style={{ color: COLOURS.device }}>● Device</span>
      <span style={{ color: COLOURS.beneficiary }}>● Beneficiary</span>
      <span style={{ color: FLAGGED }}>● Flagged by this Alert</span>
      {graph && graph.more_in_portfolio > 0 && <span>{graph.more_in_portfolio} more linked accounts not shown</span>}
      {graph && graph.out_of_scope_count > 0 && <span>{graph.out_of_scope_count} linked accounts outside your Portfolio</span>}
    </div>
  )

  if (error) return <ErrorNote message={error} />
  if (full) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-white p-4 text-slate-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Relationships of {account}</h2>
          {controls}
        </div>
        {body}
        {legend}
      </div>
    )
  }
  return (
    <Card title={`Relationships of ${account}`} action={controls}>
      {body}
      {legend}
    </Card>
  )
}
