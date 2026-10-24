const API = ''
import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import { Footer } from '../components/chrome'
import { Link } from 'react-router-dom'
import { voyanceMapStyle } from '../lib/mapstyle'
import AIExplain from '../components/analyst'
import 'maplibre-gl/dist/maplibre-gl.css'


interface Pred {
  voyage_id: string
  geojson: any
  eta: { p10_h: number; p50_h: number; p90_h: number }
  remaining_distance_nm: number
  vessel_type_group: string
  samples: number
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
        <div className="flex gap-2 items-center">
          <select className="btn" value={vid} onChange={(e) => setVid(e.target.value)}>
            {voyages.map((v: any) => (
              <option key={v.voyage_id} value={v.voyage_id}>
                {v.dep_port} → {v.arr_port} ({v.duration_h} h)
              </option>
            ))}
          </select>
          {vid && <Link to={`/voyage/${vid}`} className="chip chip-acc">full dossier →</Link>}
        </div>
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
