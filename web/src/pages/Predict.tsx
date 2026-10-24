const API = ''
import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import { Footer } from '../components/chrome'
import { voyanceMapStyle } from '../lib/mapstyle'
import 'maplibre-gl/dist/maplibre-gl.css'


interface Pred {
  voyage_id: string
  geojson: any
  eta: { p10_h: number; p50_h: number; p90_h: number }
  remaining_distance_nm: number
  vessel_type_group: string
  samples: number
}

/** minimal markdown renderer: ##/### headings, bullets, bold */
function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="space-y-2">
      {lines.map((ln, i) => {
        const bold = (t: string) => t.split(/\*\*(.+?)\*\*/g).map((seg, k) =>
          k % 2 ? <strong key={k} className="text-paper">{seg}</strong> : seg)
        if (ln.startsWith('## ')) return <h3 key={i} className="font-[family-name:var(--font-display)] text-base font-bold text-acc pt-1">{ln.slice(3)}</h3>
        if (ln.startsWith('### ')) return <h4 key={i} className="font-semibold text-acc text-sm pt-1">{ln.slice(4)}</h4>
        if (ln.startsWith('- ') || ln.startsWith('* '))
          return <div key={i} className="flex gap-2 text-[13px] leading-relaxed"><span className="text-acc">▸</span><span>{bold(ln.slice(2))}</span></div>
        if (!ln.trim()) return <div key={i} className="h-1" />
        return <p key={i} className="text-[13px] leading-relaxed">{bold(ln)}</p>
      })}
    </div>
  )
}

function PredMap({ pred, analogs }: { pred: Pred | null; analogs: any[] }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: voyanceMapStyle(),
      center: [-95, 32], zoom: 4.5,
      attributionControl: { compact: true },
    })
    map.on('load', () => { mapRef.current = map; setReady(true) })
    return () => { map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !pred) return
    // clear previous custom layers/sources on voyage switch
    for (const id of ['track-l', 'leg-l', 'cone-f', 'cone-l', 'pts-c', 'analog-l']) {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    for (const id of ['track', 'leg', 'cone', 'pts', 'analogs']) {
      if (map.getSource(id)) map.removeSource(id)
    }
    map.addSource('pred', { type: 'geojson', data: pred.geojson })
    map.addLayer({ id: 'cone-f', type: 'fill', source: 'pred', filter: ['==', 'kind', 'drift_cone'],
      paint: { 'fill-color': '#0e6e5c', 'fill-opacity': 0.16 } })
    map.addLayer({ id: 'cone-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'drift_cone'],
      paint: { 'line-color': '#0e6e5c', 'line-width': 1.5, 'line-dasharray': [2, 2] } })
    map.addLayer({ id: 'track-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'actual_track'],
      paint: { 'line-color': '#17201b', 'line-width': 3 } })
    map.addLayer({ id: 'leg-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'remaining_leg'],
      paint: { 'line-color': '#c2402e', 'line-width': 3, 'line-dasharray': [1.5, 1.5] } })
    map.addLayer({ id: 'pts-c', type: 'circle', source: 'pred', filter: ['in', 'kind', 'literal', 'destination', 'current_position'],
      paint: { 'circle-radius': 6, 'circle-color': ['match', ['get', 'kind'], 'destination', '#c2402e', '#0e6e5c'],
               'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } })
    if (analogs.length) {
      map.addSource('analogs', { type: 'geojson', data: {
        type: 'FeatureCollection',
        features: analogs.map((a) => ({ type: 'Feature',
          geometry: { type: 'LineString', coordinates: a.coords },
          properties: { vid: a.voyage_id } })) } })
      map.addLayer({ id: 'analog-l', type: 'line', source: 'analogs',
        paint: { 'line-color': '#8b948c', 'line-width': 1.5, 'line-dasharray': [4, 3] } })
    }
    const lons: number[] = []; const lats: number[] = []
    pred.geojson.features.forEach((f: any) => {
      const c = f.geometry.coordinates
      if (f.geometry.type === 'LineString') c.forEach(([x, y]: any) => { lons.push(x); lats.push(y) })
      if (f.geometry.type === 'Polygon') c[0].forEach(([x, y]: any) => { lons.push(x); lats.push(y) })
    })
    analogs.forEach((a) => a.coords.forEach(([x, y]: any) => { lons.push(x); lats.push(y) }))
    if (lons.length) map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 50, duration: 600 })
  }, [pred, analogs, ready])

  return <div ref={el} className="h-[460px] border border-rule" />
}

function AIExplain({ voyageId }: { voyageId: string }) {
  const [providers, setProviders] = useState<any[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [question, setQuestion] = useState('Why will this route drift tomorrow for this ship type?')
  const [answer, setAnswer] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    fetch(API + '/v2/ai/providers').then((r) => r.json()).then((d) => {
      setProviders(d.chain ?? [])
      const live = (d.chain ?? []).find((p: any) => p.chat_ok) ||
                   (d.chain ?? []).find((p: any) => p.reachable)
      if (live) { setProvider(live.provider); setModel(live.models?.[0] ?? '') }
    })
  }, [])
  const run = (q?: string) => {
    setBusy(true); setAnswer(null)
    fetch(API + '/v2/ai/explain', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ voyage_id: voyageId, question: q ?? question, provider: provider || null, model: model || null }) })
      .then((r) => r.json()).then(setAnswer)
      .finally(() => setBusy(false))
  }
  return (
    <div className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2" style={{ borderBottom: '1px solid var(--color-rule)', paddingBottom: 10 }}>
        <span className="microtype">AI maritime analyst · parsed answer with reference backing</span>
        <div className="flex gap-2">
          <select className="btn" value={provider} onChange={(e) => {
            setProvider(e.target.value)
            const p = providers.find((x: any) => x.provider === e.target.value)
            setModel(p?.models?.[0] ?? '')
          }}>
            {providers.map((p: any) => (
              <option key={p.provider} value={p.provider}>{p.provider}{p.chat_ok ? '' : p.reachable ? ' (chat blocked)' : ' (unreachable)'}</option>
            ))}
          </select>
          <select className="btn" value={model} onChange={(e) => setModel(e.target.value)}>
            {(providers.find((x: any) => x.provider === provider)?.models ?? []).map((m: string) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {['Why will this route drift tomorrow for this ship type?',
          'What weather risks should the fleet team watch on the remaining leg?',
          'How reliable is this ETA, and what does the historical record show?'].map((q) => (
          <button key={q} className={`btn ${question === q ? 'btn-acc' : ''}`} onClick={() => { setQuestion(q); run(q) }}>
            {q.slice(0, 34)}…
          </button>
        ))}
        <button className="btn btn-acc" onClick={() => run()} disabled={busy}>
          {busy ? 'ANALYZING…' : 'ASK'}
        </button>
      </div>
      {busy && <div className="mono mt-3 text-xs text-dim">building context packet: live forecast + historical analogs + model performance → provider…</div>}
      {answer && (
        <div className="mt-4" style={{ borderTop: '1px solid var(--color-rule)', paddingTop: 12 }}>
          <div className="microtype mb-2">
            served by {answer.provider} · {answer.model} · references below are real historical voyages
          </div>
          <Markdown text={answer.answer ?? ''} />
          {(answer.references ?? []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {answer.references.map((r: any) => (
                <a key={r.voyage_id} href={r.replay_url} className="chip chip-ok">
                  {r.voyage_id.slice(0, 18)} · {r.label}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Predict() {
  const [voyages, setVoyages] = useState<any[]>([])
  const [vid, setVid] = useState('')
  const [pred, setPred] = useState<Pred | null>(null)
  const [analogs, setAnalogs] = useState<any[]>([])
  useEffect(() => {
    fetch(API + '/v1/voyages?limit=40').then((r) => r.json()).then((d: any) => {
      if (d?.voyages) { setVoyages(d.voyages); setVid(d.voyages[0]?.voyage_id ?? '') }
    })
  }, [])
  useEffect(() => {
    if (!vid) return
    setPred(null); setAnalogs([])
    Promise.all([
      fetch(`${API}/v2/predict/route/${vid}`).then((r) => r.json()),
      fetch(`${API}/v2/predict/analogs/${vid}`).then((r) => r.json()),
    ]).then(([p, a]: any[]) => { if (p?.geojson) setPred(p); if (a?.analogs) setAnalogs(a.analogs) })
  }, [vid])

  return (
    <main className="mx-auto max-w-7xl px-5 pt-20">
      <div className="flex flex-wrap items-end justify-between gap-4 py-5">
        <div>
          <div className="microtype">the product · model + prediction, laid out</div>
          <h1 className="mt-1 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">Voyage prediction</h1>
        </div>
        <select className="btn" value={vid} onChange={(e) => setVid(e.target.value)}>
          {voyages.map((v: any) => (
            <option key={v.voyage_id} value={v.voyage_id}>
              {v.dep_port} → {v.arr_port} ({v.duration_h} h)
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="panel">
          <div className="microtype px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
            actual track · remaining leg · drift cone (P10–P90 lateral spread) · analog voyages dashed
          </div>
          <PredMap pred={pred} analogs={analogs} />
        </div>
        <div className="grid content-start gap-4">
          {pred ? (
            <>
              <div className="panel p-4">
                <div className="microtype">predicted remaining time — conformal quantiles</div>
                <div className="mt-2 grid grid-cols-3 gap-px border border-rule">
                  {[['P10', pred.eta.p10_h], ['P50', pred.eta.p50_h], ['P90', pred.eta.p90_h]].map(([k, v]) => (
                    <div key={k as string} className="px-3 py-3 text-center hairline-r">
                      <div className="big-num">{v as number}<span className="unit"> h</span></div>
                      <div className="microtype mt-1">{k as string}</div>
                    </div>
                  ))}
                </div>
                <div className="mono mt-2 text-xs text-dim">
                  {pred.remaining_distance_nm} nm to go · {pred.vessel_type_group} · {pred.samples} AIS fixes
                </div>
              </div>
              <div className="panel p-4">
                <div className="microtype">historical analogs — same destination + ship type (dashed on map)</div>
                <div className="mt-2 space-y-1">
                  {analogs.map((a) => (
                    <div key={a.voyage_id} className="mono text-[11px] flex justify-between">
                      <span className="text-dim">{a.voyage_id.slice(0, 20)}</span>
                      <span>{a.distance_nm} nm · {a.duration_h} h</span>
                    </div>
                  ))}
                  {!analogs.length && <span className="mono text-xs text-dim">none in sample window</span>}
                </div>
              </div>
            </>
          ) : (
            <div className="panel p-5 mono text-xs text-dim">selecting voyage + running quantile predictions…</div>
          )}
        </div>
      </div>

      {vid && (
        <div className="mt-4">
          <AIExplain voyageId={vid} />
        </div>
      )}

      <Footer />
    </main>
  )
}
