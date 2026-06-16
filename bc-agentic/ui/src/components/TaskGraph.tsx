import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

interface TaskNode {
  id: string
  description: string
  status: string
  agent_type: string
  depends_on: string[]
}

interface Props {
  nodes: TaskNode[]
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#6b7280',
  planning: '#3b82f6',
  running: '#f59e0b',
  complete: '#22c55e',
  failed: '#ef4444',
  cancelled: '#9ca3af',
  awaiting_approval: '#a855f7',
}

export default function TaskGraph({ nodes }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || !nodes.length) return

    const width = svgRef.current.clientWidth || 800
    const height = 300

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const g = svg.append('g').attr('transform', 'translate(40, 40)')

    // Build links
    const links: { source: string; target: string }[] = []
    nodes.forEach((n) => {
      n.depends_on.forEach((dep) => links.push({ source: dep, target: n.id }))
    })

    // Layout: simple horizontal topo sort
    const levels: Map<string, number> = new Map()
    const visited = new Set<string>()

    function assignLevel(id: string, level: number) {
      if (visited.has(id)) return
      visited.add(id)
      levels.set(id, Math.max(level, levels.get(id) ?? 0))
      const children = links.filter((l) => l.source === id).map((l) => l.target)
      children.forEach((c) => assignLevel(c, level + 1))
    }

    const roots = nodes.filter((n) => !n.depends_on.length)
    roots.forEach((r) => assignLevel(r.id, 0))
    nodes.forEach((n) => { if (!levels.has(n.id)) levels.set(n.id, 0) })

    const maxLevel = Math.max(...Array.from(levels.values()), 0)
    const levelWidth = Math.max(120, (width - 80) / (maxLevel + 1))
    const nodesByLevel: Map<number, string[]> = new Map()
    levels.forEach((lv, id) => {
      if (!nodesByLevel.has(lv)) nodesByLevel.set(lv, [])
      nodesByLevel.get(lv)!.push(id)
    })

    const positions: Map<string, { x: number; y: number }> = new Map()
    nodesByLevel.forEach((ids, lv) => {
      const yStep = (height - 80) / Math.max(ids.length, 1)
      ids.forEach((id, i) => {
        positions.set(id, { x: lv * levelWidth, y: i * yStep + yStep / 2 })
      })
    })

    // Draw links
    g.selectAll('.link')
      .data(links)
      .join('line')
      .attr('class', 'link')
      .attr('x1', (d) => positions.get(d.source)?.x ?? 0)
      .attr('y1', (d) => positions.get(d.source)?.y ?? 0)
      .attr('x2', (d) => positions.get(d.target)?.x ?? 0)
      .attr('y2', (d) => positions.get(d.target)?.y ?? 0)
      .attr('stroke', '#374151')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrow)')

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#374151')

    // Draw nodes
    const nodeG = g.selectAll('.node')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .attr('transform', (d) => {
        const pos = positions.get(d.id) ?? { x: 0, y: 0 }
        return `translate(${pos.x}, ${pos.y})`
      })

    nodeG.append('circle')
      .attr('r', 16)
      .attr('fill', (d) => STATUS_COLORS[d.status] ?? '#6b7280')
      .attr('stroke', '#1f2937')
      .attr('stroke-width', 2)

    nodeG.append('title').text((d) => d.description)

    nodeG.append('text')
      .attr('y', 30)
      .attr('text-anchor', 'middle')
      .attr('fill', '#d1d5db')
      .attr('font-size', '9px')
      .text((d) => d.agent_type)

  }, [nodes])

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">Task Graph</h3>
      {nodes.length === 0 ? (
        <p className="text-gray-600 text-sm">No tasks planned yet</p>
      ) : (
        <svg ref={svgRef} className="w-full" style={{ height: 300 }} />
      )}
      <div className="flex gap-3 mt-3 flex-wrap">
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <div key={status} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-xs text-gray-500">{status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
