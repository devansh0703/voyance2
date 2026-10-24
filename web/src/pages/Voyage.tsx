import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as maplibregl from 'maplibre-gl'
import * as echarts from 'echarts'
import { Footer } from '../components/chrome'
import AIExplain from '../components/analyst'
import { voyanceMapStyle } from '../lib/mapstyle'
import 'maplibre-gl/dist/maplibre-gl.css'

const API = ''
const AXIS = { axisLine: { lineStyle: { color: '#d7dad2' } }, axisLabel: { color: '#5d675f', fontSize: 10, fontFamily: 'JetBrains Mono' }, splitLine: { lineStyle: { color: '#e4e7df' } } }

async function j(url: string): Promise<any> {
  try { const r = await fetch(API + url); return r.ok ? await r.json() : null } catch { return null }
}

function EChart({ option, height = 220 }: { option: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const c = echarts.init(ref.current)
    c.setOption(option)
    const on = () => c.resize()
    window.addEventListener('resize', on)
    return () => { window.removeEventListener('resize', on); c.dispose() }
  }, [option])
  return <div ref={ref} style={{ height }} />
}

function VoyageMap({ pred, analogs }: { pred: any; analogs: any[] }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current, style: voyanceMapStyle(),
      center: [-95, 32], zoom: 4.5, attributionControl: { compact: true },
    })
    map.on('load', () => { mapRef.current = map; setReady(true) })
    return () => { map.remove(); mapRef.current = null }
  }, [])
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !pred) return
    for (const id of ['track-l', 'leg-l', 'cone-f', 'cone-l', 'pts-c', 'analog-l'])
      if (map.getLayer(id)) map.removeLayer(id)
    for (const id of ['pred', 'analogs'])
      if (map.getSource(id)) map.removeSource(id)
    map.addSource('pred', { type: 'geojson', data: pred.geojson })
    map.addLayer({ id: 'cone-f', type: 'fill', source: 'pred', filter: ['==', 'kind', 'drift_cone'],
      paint: { 'fill-color': '#0e6e5c', 'fill-opacity': 0.16 } })
    map.addLayer({ id: 'cone-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'drift_cone'],
      paint: { 'line-color': '#0e6e5c', 'line-width': 1.5, 'line-dasharray': [2, 2] } })
    map.addLayer({ id: 'track-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'actual_track'],
      paint: { 'line-color': '#17201b', 'line-width': 3 } })
    map.addLayer({ id: 'leg-l', type: 'line', source: 'pred', filter: ['==', 'kind', 'remaining_leg'],
      paint: { 'line-color': '#c2402e', 'line-width': 3, 'line-dasharray': [1.5, 1.5] } })
    map.addLayer({ id: 'pts-c', type: 'circle', source: 'pred',
      filter: ['in', 'kind', 'literal', 'destination', 'current_position'],
      paint: { 'circle-radius': 6,
               'circle-color': ['match', ['get', 'kind'], 'destination', '#c2402e', '#0e6e5c'],
               'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } })
    if (analogs.length) {
      map.addSource('analogs', { type: 'geojson', data: { type: 'FeatureCollection',
        features: analogs.map((a) => ({ type: 'Feature',
          geometry: { type: 'LineString', coordinates: a.coords }, properties: {} })) } })
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
  return <div ref={el} className="h-[440px] border border-rule" />
}

function Replay({ rep }: { rep: any }) {
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (!playing || !rep) return
    const t = setInterval(() => setIdx((i) => {
      if (i >= rep.coords.length - 1) { setPlaying(false); return i }
      return i + 1
    }), 220)
    return () => clearInterval(t)
  }, [playing, rep])
  if (!rep) return <div className="mono text-xs text-dim p-4">replay bundle loading…</div>
  const cur = rep.fsm?.[Math.min(idx, rep.fsm.length - 1)]
  return (
    <div>
      <div className="flex items-center gap-3 px-4 pt-3">
        <button className="btn btn-acc" onClick={() => setPlaying(!playing)}>{playing ? 'PAUSE' : 'PLAY'}</button>
        <input type="range" min={0} max={rep.coords.length - 1} value={idx}
          onChange={(e) => setIdx(+e.target.value)} className="flex-1" />
        <span className="mono text-xs text-dim">{idx + 1}/{rep.coords.length}</span>
      </div>
      <div className="px-4 py-2 flex flex-wrap gap-1.5">
        {cur && <span className="chip chip-acc">FSM {cur.state} · {cur.phase} · {cur.sog_band}</span>}
        {(rep.gaps?.gaps ?? []).slice(0, 3).map((g: any, i: number) =>
          <span key={i} className="chip chip-bad">AIS drop {g.gap_min} min</span>)}
        {rep.gaps && <span className="chip chip-ok">coverage {(rep.gaps.coverage * 100).toFixed(1)}%</span>}
      </div>
      <EChart height={170} option={{
        grid: { left: 44, right: 12, top: 16, bottom: 24 },
        xAxis: { type: 'category', data: rep.sog.map((_: any, i: number) => i), ...AXIS },
        yAxis: { type: 'value', name: 'SOG kn', ...AXIS },
        series: [
          { type: 'line', data: rep.sog, symbol: 'none', lineStyle: { color: '#aab1a5', width: 1 } },
          { type: 'line', data: rep.sog_smoothed, symbol: 'none',
            lineStyle: { color: '#0e6e5c', width: 2 }, areaStyle: { color: 'rgba(14,110,92,0.08)' } },
        ], tooltip: { trigger: 'axis' } }} />
      <EChart height={150} option={{
        grid: { left: 44, right: 12, top: 16, bottom: 24 },
        xAxis: { type: 'category', data: rep.fuel_series_t_day.map((_: any, i: number) => i), ...AXIS },
        yAxis: { type: 'value', name: 'fuel t/day', ...AXIS },
        series: [{ type: 'line', data: rep.fuel_series_t_day, symbol: 'none',
                   lineStyle: { color: '#a86a00', width: 2 } }], tooltip: { trigger: 'axis' } }} />
    </div>
  )
}

export default function Voyage() {
  const { id } = useParams()
  const [pred, setPred] = useState<any>(null)
  const [analogs, setAnalogs] = useState<any[]>([])
  const [rep, setRep] = useState<any>(null)
  const [bathy, setBathy] = useState<any>(null)
  const [meta, setMeta] = useState<any>(null)
  const [allVoyages, setAllVoyages] = useState<any[]>([])
  const [q, setQ] = useState('')

  useEffect(() => {
    fetch(API + '/v1/voyages?limit=10000').then((r) => r.json()).then((d) => setAllVoyages(d?.voyages ?? []))
  }, [])
  useEffect(() => {
    if (!id) return
    setPred(null); setAnalogs([]); setRep(null); setBathy(null)
    j(`/v2/predict/route/${id}`).then((p) => p && setPred(p))
    j(`/v2/predict/analogs/${id}`).then((a) => a && setAnalogs(a.analogs ?? []))
    j(`/v2/analytics/replay/${id}`).then((r) => r && setRep(r))
    j(`/v2/live/bathymetry?voyage_id=${id}`).then((b) => b && setBathy(b))
    j(`/v1/voyages?limit=10000`).then((d) => {
      const m = (d?.voyages ?? []).find((v: any) => v.voyage_id === id)
      setMeta(m)
    })
  }, [id])

  const picker = q
    ? allVoyages.filter((v) => (v.dep_port + ' ' + v.arr_port + ' ' + v.vessel_type_group + ' ' + v.month)
        .toLowerCase().includes(q.toLowerCase())).slice(0, 30)
    : []

  return (
    <main className="mx-auto max-w-7xl px-5 pt-20">
      <div className="flex flex-wrap items-end justify-between gap-4 py-5">
        <div>
          <div className="microtype">voyage dossier · everything about one voyage</div>
          <h1 className="mt-1 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">
            {meta ? `${meta.dep_port} → ${meta.arr_port}` : id?.slice(0, 24) + '…'}
          </h1>
          {meta && (
            <div className="mono mt-1 text-xs text-dim">
              {meta.vessel_type_group} · {meta.duration_h} h · {meta.distance_nm} nm · {meta.month}
            </div>
          )}
        </div>
        <div className="panel px-3 py-2 flex items-center gap-2 w-[340px]">
          <span className="microtype">go to</span>
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="search any voyage: port, type, month…"
            className="mono flex-1 bg-transparent text-xs text-paper outline-none placeholder:text-dim" />
          <span className="chip">{allVoyages.length.toLocaleString()}</span>
        </div>
      </div>

      {picker.length > 0 && (
        <div className="panel mb-4 max-h-56 overflow-y-auto">
          {picker.map((v) => (
            <Link key={v.voyage_id} to={`/voyage/${v.voyage_id}`}
              onClick={() => setQ('')}
              className="flex justify-between px-4 py-2 mono text-xs hover:bg-panel2">
              <span>{v.dep_port} → {v.arr_port}</span>
              <span className="text-dim">{v.vessel_type_group} · {v.duration_h} h · {v.month}</span>
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="panel">
          <div className="microtype px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
            track · remaining leg · drift cone · analog voyages (dashed)
          </div>
          <VoyageMap pred={pred} analogs={analogs} />
        </div>
        <div className="grid content-start gap-4">
          <div className="panel p-4">
            <div className="microtype">predicted remaining time</div>
            {pred ? (
              <>
                <div className="mt-2 grid grid-cols-3 gap-px border border-rule">
                  {[['P10', pred.eta.p10_h], ['P50', pred.eta.p50_h], ['P90', pred.eta.p90_h]].map(([k, v]: any) => (
                    <div key={k} className="px-3 py-3 text-center hairline-r">
                      <div className="big-num">{v}<span className="unit"> h</span></div>
                      <div className="microtype mt-1">{k}</div>
                    </div>
                  ))}
                </div>
                <div className="mono mt-2 text-xs text-dim">
                  {pred.remaining_distance_nm} nm to go · {pred.vessel_type_group} · {pred.samples} fixes
                </div>
              </>
            ) : <div className="mono mt-2 text-xs text-dim">computing quantiles…</div>}
          </div>
          <div className="panel p-4">
            <div className="microtype">historical analogs — same port + ship type</div>
            <div className="mt-2 space-y-1">
              {analogs.map((a) => (
                <Link key={a.voyage_id} to={`/voyage/${a.voyage_id}`} className="mono text-[11px] flex justify-between hover:text-acc">
                  <span className="text-dim truncate" style={{ maxWidth: 170 }}>{a.voyage_id.slice(0, 20)}</span>
                  <span>{a.distance_nm} nm · {a.duration_h} h</span>
                </Link>
              ))}
              {!analogs.length && <span className="mono text-xs text-dim">{pred ? 'none in sample window' : '…'}</span>}
            </div>
          </div>
          <div className="panel p-4">
            <div className="microtype">depth profile along track · ETOPO1</div>
            {bathy?.profile?.length ? (
              <EChart height={150} option={{
                grid: { left: 44, right: 10, top: 14, bottom: 22 },
                xAxis: { type: 'category', data: bathy.profile.map((_: any, i: number) => i), ...AXIS },
                yAxis: { type: 'value', inverse: true, name: 'm', ...AXIS },
                series: [{ type: 'line', data: bathy.profile.map((p: any) => p.depth_m), smooth: true,
                  showSymbol: false, lineStyle: { color: '#0d7d8c', width: 2 } }] }} />
            ) : <div className="mono mt-2 text-xs text-dim">sampling depths…</div>}
          </div>
        </div>
      </div>

      <div className="mt-4 panel">
        <div className="microtype px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
          track replay · playback scrubber · SOG + fuel series · gap indicators · FSM states
        </div>
        <Replay rep={rep} />
      </div>

      {id && (
        <div className="mt-4">
          <AIExplain voyageId={id} />
        </div>
      )}

      <Footer />
    </main>
  )
}
