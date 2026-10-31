import type { Alert, Graph } from '../api'
import { Card } from '../ui'

const WIDTH = 760
const HEIGHT = 400
const CENTRE = { x: WIDTH / 2, y: HEIGHT / 2 }
const INNER = { x: 190, y: 105 }
const OUTER = { x: 330, y: 170 }
const SIZE = 9
const COLOURS = { account: '#0f172a', device: '#2563eb', beneficiary: '#7c3aed', flagged: '#dc2626' }

type Point = { x: number; y: number }

function ring(index: number, count: number, radius: Point): Point {
  const angle = (index / Math.max(1, count)) * Math.PI * 2 - Math.PI / 2
  return { x: CENTRE.x + radius.x * Math.cos(angle), y: CENTRE.y + radius.y * Math.sin(angle) }
}

function flaggedIds(alert: Alert) {
  const ids = new Set<string>()
  if (alert.device_id) ids.add(alert.device_id)
  for (const record of alert.supporting_records) {
    const beneficiary = record.data.beneficiary_id
    if (typeof beneficiary === 'string') ids.add(beneficiary)
  }
  return ids
}

function Marker({ type, at, colour }: { type: string; at: Point; colour: string }) {
  if (type === 'device') {
    return <rect x={at.x - SIZE} y={at.y - SIZE} width={SIZE * 2} height={SIZE * 2} rx={2} fill={colour} />
  }
  if (type === 'beneficiary') {
    const points = [[0, -SIZE - 2], [SIZE + 2, 0], [0, SIZE + 2], [-SIZE - 2, 0]]
    return <polygon points={points.map(([x, y]) => `${at.x + x},${at.y + y}`).join(' ')} fill={colour} />
  }
  return <circle cx={at.x} cy={at.y} r={SIZE} fill={colour} />
}

export default function EntityGraph({ graph, alert }: { graph: Graph; alert: Alert }) {
  const flagged = flaggedIds(alert)
  const [focus, ...others] = graph.nodes
  const hubs = others.filter((n) => n.type !== 'account')
  const linked = others.filter((n) => n.type === 'account')
  const places = new Map<string, Point>([[focus.id, CENTRE]])
  hubs.forEach((n, i) => places.set(n.id, ring(i, hubs.length, INNER)))
  linked.forEach((n, i) => places.set(n.id, ring(i + 0.5, linked.length, OUTER)))

  return (
    <Card title={`Relationships of ${focus.id}`} tooltip="Select an Alert to see its account. Red marks what this Alert flagged.">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label={`Relationship graph for ${focus.id}`}>
        {graph.edges.map((e) => {
          const from = places.get(e.source)
          const to = places.get(e.target)
          if (!from || !to) return null
          const hot = flagged.has(e.target)
          return (
            <line
              key={`${e.source}-${e.target}-${e.label}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={hot ? COLOURS.flagged : '#94a3b8'}
              strokeWidth={hot ? 2 : 1}
            />
          )
        })}
        {graph.nodes.map((n, i) => {
          const at = places.get(n.id)
          if (!at) return null
          const colour = flagged.has(n.id) ? COLOURS.flagged : COLOURS[n.type as 'account' | 'device' | 'beneficiary']
          return (
            <g key={n.id}>
              <Marker type={n.type} at={at} colour={colour} />
              <text x={at.x} y={at.y + SIZE + 14} textAnchor="middle" fontSize={i === 0 ? 13 : 11} fontWeight={i === 0 ? 600 : 400} fill="currentColor">
                {n.label}
              </text>
              {n.type === 'beneficiary' && n.label !== n.id && (
                <text x={at.x} y={at.y + SIZE + 27} textAnchor="middle" fontSize={10} fill="#64748b">{n.id}</text>
              )}
            </g>
          )
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span><span style={{ color: COLOURS.account }}>●</span> Account</span>
        <span><span style={{ color: COLOURS.device }}>■</span> Device</span>
        <span><span style={{ color: COLOURS.beneficiary }}>◆</span> Beneficiary</span>
        <span><span style={{ color: COLOURS.flagged }}>●</span> Flagged by this Alert</span>
        {graph.more_in_portfolio > 0 && <span>{graph.more_in_portfolio} more linked accounts not shown</span>}
        {graph.out_of_scope_count > 0 && <span>{graph.out_of_scope_count} linked accounts outside your Portfolio</span>}
      </div>
    </Card>
  )
}
