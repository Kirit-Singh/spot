import cytoscape from 'cytoscape'
import { useEffect, useRef } from 'react'
import { CENTER, EDGES } from '../data/seedGraph'
import { EVIDENCE } from '../design/tokens'

const R = 250

const style = [
  {
    selector: 'node',
    style: {
      'background-color': '#FFFFFF', 'border-width': 1.6, 'border-color': 'data(color)',
      label: 'data(label)', 'font-size': 11, 'font-family': 'Inter Tight, sans-serif',
      color: '#1E1B16', width: 26, height: 26,
      'text-valign': 'data(valign)', 'text-halign': 'data(halign)',
      'text-margin-x': 'data(mx)', 'text-margin-y': 'data(my)',
    },
  },
  {
    selector: "node[kind='hit']",
    style: {
      shape: 'round-rectangle', width: 128, height: 70, 'border-width': 3, 'border-color': '#111827',
      'font-family': 'Newsreader, serif', 'font-size': 23,
      'text-valign': 'center', 'text-halign': 'center', 'text-margin-x': 0, 'text-margin-y': 0,
      'z-index': 10,
    },
  },
  {
    selector: 'edge',
    style: { 'line-color': 'data(color)', width: 'data(width)', 'curve-style': 'bezier', opacity: 0.9 },
  },
  { selector: 'edge[?dashed]', style: { 'line-style': 'dashed', opacity: 0.5 } },
] as unknown as cytoscape.StylesheetCSS[]

export function EvidenceGraph() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const elements: cytoscape.ElementDefinition[] = [
      {
        data: { id: CENTER.id, label: CENTER.label, kind: 'hit' },
        position: { x: 0, y: 0 },
      },
      ...EDGES.flatMap((e) => {
        const rad = (e.angle * Math.PI) / 180
        const cos = Math.cos(rad)
        const sin = Math.sin(rad)
        const halign = cos > 0.35 ? 'right' : cos < -0.35 ? 'left' : 'center'
        const valign = sin > 0.35 ? 'top' : sin < -0.35 ? 'bottom' : 'center'
        return [
          {
            data: {
              id: e.id, label: e.label, color: EVIDENCE[e.ev].color,
              halign, valign,
              mx: halign === 'right' ? 6 : halign === 'left' ? -6 : 0,
              my: valign === 'bottom' ? 6 : valign === 'top' ? -6 : 0,
            },
            position: { x: R * cos, y: -R * sin },
          },
          {
            data: {
              id: `edge-${e.id}`, source: CENTER.id, target: e.id,
              color: EVIDENCE[e.ev].color, width: 1.5 + e.weight * 3.5,
              dashed: e.state === 'untested' ? 1 : 0,
            },
          },
        ]
      }),
    ]
    const cy = cytoscape({
      container: el,
      elements,
      style,
      layout: { name: 'preset', fit: true, padding: 72 } as cytoscape.LayoutOptions,
    })
    const ro = new ResizeObserver(() => {
      cy.resize()
      cy.fit(undefined, 72)
    })
    ro.observe(el)
    return () => {
      ro.disconnect()
      cy.destroy()
    }
  }, [])

  return <div ref={ref} className="h-full w-full" />
}
