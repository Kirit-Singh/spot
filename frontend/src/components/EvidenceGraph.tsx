import cytoscape from 'cytoscape'
// @ts-expect-error cytoscape-fcose ships no type declarations
import fcose from 'cytoscape-fcose'
import { useEffect, useRef } from 'react'
import { CENTER, EDGES } from '../data/seedGraph'
import { EVIDENCE } from '../design/tokens'

cytoscape.use(fcose)

const style = [
  {
    selector: 'node',
    style: {
      'background-color': '#FFFFFF', 'border-width': 1.6, 'border-color': 'data(color)',
      label: 'data(label)', 'font-size': 11, 'font-family': 'Inter Tight, sans-serif',
      color: '#1E1B16', width: 26, height: 26, 'text-valign': 'bottom', 'text-margin-y': 6,
    },
  },
  {
    selector: "node[kind='hit']",
    style: {
      shape: 'round-rectangle', width: 122, height: 68, 'border-width': 3, 'border-color': '#111827',
      'font-family': 'Newsreader, serif', 'font-size': 22, 'text-valign': 'center', 'text-margin-y': 0,
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
      { data: { id: CENTER.id, label: CENTER.label, kind: 'hit' } },
      ...EDGES.flatMap((e) => {
        const color = EVIDENCE[e.ev].color
        return [
          { data: { id: e.id, label: e.label, color } },
          {
            data: {
              id: `edge-${e.id}`, source: CENTER.id, target: e.id,
              color, width: 1.5 + e.weight * 3.5, dashed: e.state === 'untested' ? 1 : 0,
            },
          },
        ]
      }),
    ]
    const cy = cytoscape({
      container: el,
      elements,
      style,
      layout: { name: 'fcose', animate: false, nodeSeparation: 90 } as cytoscape.LayoutOptions,
    })
    return () => {
      cy.destroy()
    }
  }, [])

  return <div ref={ref} className="h-full w-full" />
}
