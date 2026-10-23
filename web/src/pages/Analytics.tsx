import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import * as echarts from 'echarts'
import { Footer } from '../components/chrome'
import 'maplibre-gl/dist/maplibre-gl.css'

const API = ''
async function j<T>(url: string): Promise<T | null> {
  try { const r = await fetch(API + url); return r.ok ? await r.json() : null } catch { return null }
}

function EChart({ option, height = 300 }: { option: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const c = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    c.setOption(option)
    const on = () => c.resize()
    window.addEventListener('resize', on)
    return () => { window.removeEventListener('resize', on); c.dispose() }
  }, [option])
  return <div ref={ref} style={{ height }} />
}

const AXIS = { axisLine: { lineStyle: { color: '#d7dad2' } }, axisLabel: { color: '#5d675f', fontSize: 10, fontFamily: 'JetBrains Mono' }, splitLine: { lineStyle: { color: '#e4e7df' } } }

/* ── H3 density heatmap ── */
function HexHeat({ data }: { data: any[] }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#dfe7ea' } }] },
      center: [-95, 35], zoom: 3.6, attributionControl: false,
    })
    map.on('load', () => { mapRef.current = map; setReady(true) })
    return () => { map.remove(); mapRef.current = null }
  }, [])
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !data?.length) return
    const fc = { type: 'FeatureCollection', features: data.map((h) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [h.lng, h.lat] },
      properties: { n: h.n } })) } as any
    if (map.getSource('hex')) (map.getSource('hex') as any).setData(fc)
    else {
      map.addSource('hex', { type: 'geojson', data: fc })
      map.addLayer({ id: 'hex', type: 'heatmap', source: 'hex',
        paint: { 'heatmap-weight': ['interpolate', ['linear'], ['get', 'n'], 1, 0, 300, 1],
                 'heatmap-intensity': 1.1, 'heatmap-radius': 28,
                 'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(13,16,14,0)', 0.3, '#1d3a2f', 0.55, '#6fdc8c', 0.8, '#ffb454', 1, '#ff6b57'] } })
    }
  }, [data, ready])
  return <div ref={el} className="h-[380px] border border-rule" />
}

/* ── depth profile ── */
function DepthProfile() {
  const [prof, setProf] = useState<any>(null)
  const [voy, setVoy] = useState('')
  const [list, setList] = useState<string[]>([])
  useEffect(() => {
    j('/v1/voyages?limit=30').then((d: any) => {
      if (!d?.voyages) return
      setList(d.voyages.map((v: any) => v.voyage_id))
      setVoy(d.voyages[0]?.voyage_id ?? '')
    })
  }, [])
  useEffect(() => {
    if (voy) j(`/v2/live/bathymetry?voyage_id=${voy}`).then(setProf)
  }, [voy])
  const pts = prof?.profile ?? []
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5 hairline-b">
        <span className="microtype">bathymetric depth profile · EMODnet DTM via OpenTopoData (European waters)</span>
        <select className="btn" value={voy} onChange={(e) => setVoy(e.target.value)}>
          {list.map((v) => <option key={v} value={v}>{v.slice(0, 22)}</option>)}
        </select>
      </div>
      <EChart height={260} option={{
        grid: { left: 50, right: 16, top: 24, bottom: 30 },
        xAxis: { type: 'category', data: pts.map((_: any, i: number) => i), ...AXIS },
        yAxis: { type: 'value', inverse: true, name: 'depth m', nameTextStyle: { color: '#8b948c' }, ...AXIS },
        series: [{ type: 'line', data: pts.map((p: any) => p.depth_m), smooth: true, showSymbol: false,
                   lineStyle: { color: '#7adccf', width: 2 }, areaStyle: { color: 'rgba(122,220,207,0.10)' } }],
        tooltip: { trigger: 'axis' },
      }} />
    </div>
  )
}

/* ── route optimizer ── */
function RouteOptimizer() {
  const [result, setResult] = useState<any>(null)
  const [algo, setAlgo] = useState('astar')
  const [err, setErr] = useState('')
  const run = () => {
    j(`/v2/analytics/route?src=0&dst=50&algorithm=${algo}`).then((d: any) => {
      if (d) { setResult(d); setErr('') } else setErr('graph loading — run precompute_v2')
    })
  }
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5 hairline-b">
        <span className="microtype">maritime graph routing · networkx {algo}</span>
        <div className="flex gap-2">
          <select className="btn" value={algo} onChange={(e) => setAlgo(e.target.value)}>
            <option value="astar">A*</option><option value="dijkstra">Dijkstra</option>
          </select>
          <button className="btn btn-acc" onClick={run}>RUN</button>
        </div>
      </div>
      <div className="p-4">
        {result ? (
          <div className="mono text-xs">
            <div className="text-ok">path found — {result.path.length} hops · {result.distance_nm} nm total</div>
            <div className="mt-2 text-dim break-all">{result.path.join(' → ')}</div>
          </div>
        ) : <div className="mono text-xs text-dim">{err || 'press RUN — great-circle weighted port graph, 600 nm edge cap'}</div>}
      </div>
    </div>
  )
}

/* ── fuel & CO2 ── */
function FuelPanel() {
  const [state, setState] = useState({ sog: 12, wave: 1.5, dwt: 50000, len: 180, dist: 500 })
  const [r, setR] = useState<any>(null)
  useEffect(() => {
    j(`/v2/analytics/fuel?sog_kn=${state.sog}&wave_height_m=${state.wave}&vessel_length_m=${state.len}&dwt_t=${state.dwt}&distance_nm=${state.dist}`).then(setR)
  }, [state])
  return (
    <div className="panel">
      <div className="microtype px-4 py-2.5 hairline-b">fuel & emissions · ITTC-1978 Cf · Townsin-Glover added resistance · IMO C-factors</div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px">
        {([['sog', 'SOG kn'], ['wave', 'wave m'], ['dwt', 'DWT t'], ['len', 'L m'], ['dist', 'dist nm']] as const).map(([k, label]) => (
          <div key={k} className="p-3 hairline-r">
            <div className="microtype">{label}</div>
            <input type="number" className="mono w-full bg-transparent text-sm text-paper outline-none"
              value={(state as any)[k]} onChange={(e) => setState({ ...state, [k]: +e.target.value })} />
          </div>
        ))}
      </div>
      {r && (
        <div className="hairline-t grid grid-cols-2 gap-px">
          <div className="p-4 hairline-r">
            <div className="big-num">{r.voyage_fuel_t}<span className="unit"> t fuel</span></div>
            <div className="mono mt-1 text-xs text-dim">{r.fuel_t_per_day} t/day · {r.power_calm_kw} kW calm + {r.power_added_kw} kW wave</div>
          </div>
          <div className="p-4">
            <div className="big-num text-ok">{r.co2_t}<span className="unit"> t CO2</span></div>
            <div className="mono mt-1 text-xs text-dim">C_f {r.cf} ({r.carbon_intensity_g_per_ton_nm} g/t·nm intensity)</div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── anchorages + queues ── */
function Anchorages() {
  const [a, setA] = useState<any>(null)
  useEffect(() => { j('/v2/analytics/anchorages').then(setA) }, [])
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5 hairline-b">
        <span className="microtype">anchorage occupancy · HDBSCAN · Little's Law · M/M/c</span>
        <span className="chip">{a?.anchorages?.length ?? '…'} clusters</span>
      </div>
      <table className="dense">
        <thead><tr><th>CLUSTER</th><th>LAT</th><th>LNG</th><th>OCCUPANCY</th><th>λ/h</th><th>M/M/c WAIT h</th><th>ρ</th></tr></thead>
        <tbody>
          {(a?.anchorages ?? []).slice(0, 10).map((c: any) => (
            <tr key={c.cluster}>
              <td>#{c.cluster}</td><td>{c.lat}</td><td>{c.lng}</td><td>{c.occupancy}</td>
              <td>{(c.occupancy / 168).toFixed(3)}</td>
              <td>{c.queue_mmc?.mean_wait_h ?? '—'}</td>
              <td>{c.queue_mmc?.utilization ?? '—'}</td>
            </tr>
          ))}
          {!a && <tr><td colSpan={7} className="text-dim">running HDBSCAN…</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

/* ── anomaly gauge ── */
function AnomalyGauge() {
  const [s, setS] = useState<any>(null)
  const [inp, setInp] = useState({ lat: 33.7, lon: -118.2, sog: 0.2, rem: 80 })
  useEffect(() => {
    j(`/v2/analytics/anomaly?lat=${inp.lat}&lon=${inp.lon}&sog=${inp.sog}&remaining_distance_nm=${inp.rem}`).then(setS)
  }, [inp])
  const score = s?.scores?.composite_0_1
  return (
    <div className="panel p-4">
      <div className="microtype hairline-b pb-2.5">anomaly scoring · IsolationForest + GMM + Mahalanobis</div>
      <div className="mt-3 flex items-center gap-6">
        <div>
          <div className="big-num" style={{ color: score > 0.6 ? '#ff6b57' : score > 0.3 ? '#ffcf5c' : '#6fdc8c' }}>
            {score != null ? (score * 100).toFixed(1) : '…'}<span className="unit"> /100</span>
          </div>
          <div className="mono mt-1 text-xs text-dim">iso {s?.scores?.isolation_forest ?? '…'} · mah {s?.scores?.mahalanobis ?? '…'}</div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {(['lat', 'lon', 'sog', 'rem'] as const).map((k, i) => (
            <label key={k} className="mono text-dim">
              {['lat', 'lon', 'sog', 'rem nm'][i]}
              <input type="number" className="ml-2 w-20 bg-transparent text-paper outline-none border border-rule px-1"
                value={(inp as any)[k]} onChange={(e) => setInp({ ...inp, [k]: +e.target.value })} />
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── biodiversity chips ── */
function BioChips() {
  const [b, setB] = useState<any>(null)
  useEffect(() => { j('/v2/live/overlays/biodiversity?lat=59.9&lon=23.5').then(setB) }, [])
  const names = [...(b?.obis ?? []).slice(0, 6).map((x: any) => x.scientificName),
                 ...(b?.gbif ?? []).slice(0, 4).map((x: any) => x.scientificName)].filter(Boolean)
  return (
    <div className="panel p-4">
      <div className="microtype hairline-b pb-2.5">occurrence chips · OBIS + GBIF (Gulf of Finland cell)</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {names.length ? names.map((n: string, i: number) => <span key={i} className="chip chip-ok">{n}</span>)
          : <span className="mono text-xs text-dim">loading open occurrence records…</span>}
      </div>
    </div>
  )
}

/* ── HMM regime demo ── */
function HmmPanel() {
  const [h, setH] = useState<any>(null)
  useEffect(() => {
    const series = Array.from({ length: 24 }, (_, i) => (12 + 6 * Math.sin(i / 3) + (i > 16 ? -8 : 0) + Math.random()).toFixed(1)).join(',')
    j(`/v2/analytics/hmm?sog_series=${series}`).then(setH)
  }, [])
  return (
    <div className="panel">
      <div className="microtype px-4 py-2.5 hairline-b">voyage regimes · Gaussian HMM over SOG (hmmlearn)</div>
      {h ? (
        <>
          <EChart height={200} option={{
            grid: { left: 40, right: 14, top: 20, bottom: 28 },
            xAxis: { type: 'category', data: h.states.map((_: any) => _), ...AXIS },
            yAxis: { type: 'value', name: 'SOG kn', ...AXIS },
            series: [{ type: 'line', step: 'middle', data: h.states.map((s: any) => h.state_means_kn[s]), ...AXIS,
                       lineStyle: { color: '#ffb454', width: 2 } }],
            tooltip: { trigger: 'axis' },
          }} />
          <div className="px-4 pb-3 mono text-xs text-dim">state means: {h.state_means_kn.join(' · ')} kn → drift / maneuver / transit</div>
        </>
      ) : <div className="p-4 mono text-xs text-dim">decoding regimes…</div>}
    </div>
  )
}


/* ── historical track replay + scrubber + gaps + FSM + fuel series ── */
function ReplayPanel() {
  const [list, setList] = useState<string[]>([])
  const [vid, setVoy] = useState('')
  const [rep, setRep] = useState<any>(null)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    fetch(API + '/v1/voyages?limit=25').then((r) => r.json()).then((d: any) => {
      if (!d?.voyages) return
      setList(d.voyages.map((v: any) => v.voyage_id))
      setVoy(d.voyages[0]?.voyage_id ?? '')
    })
  }, [])
  useEffect(() => {
    if (vid) fetch(`${API}/v2/analytics/replay/${vid}`).then((r) => r.json()).then((d) => {
      setRep(d); setIdx(0)
      if ((d?.coords?.length ?? 0) < 8) {  // thin track: try the next voyage ids
        const next = list.filter((x) => x !== vid)[0]
        if (next) setVoy(next)
      }
    })
  }, [vid])
  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: { version: 8,
        sources: { gebco: { type: 'raster',
          tiles: ['https://wms.gebco.net/mapserv?request=GetMap&service=WMS&version=1.1.1&format=image/png&STYLES=default&layers=GEBCO_LATEST_SUB_ICE_TOPO&width=512&height=512&bbox={bbox-epsg-3857}'],
          tileSize: 512 } },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#dfe7ea' } },
          { id: 'gebco', type: 'raster', source: 'gebco', paint: { 'raster-opacity': 0.9 } }] },
      center: [-90, 30], zoom: 4.2, attributionControl: { compact: true } })
    map.on('load', () => { mapRef.current = map; setReady(true) })
    return () => { map.remove(); mapRef.current = null }
  }, [])
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !rep?.coords?.length) return
    const line = { type: 'Feature', geometry: { type: 'LineString', coordinates: rep.coords }, properties: {} }
    const upto = rep.coords.slice(0, idx + 1)
    const flown = { type: 'Feature', geometry: { type: 'LineString', coordinates: upto.length > 1 ? upto : [rep.coords[0], rep.coords[0]] }, properties: {} }
    const pos = { type: 'FeatureCollection', features: [{
      type: 'Feature', geometry: { type: 'Point', coordinates: rep.coords[Math.min(idx, rep.coords.length - 1)] },
      properties: {} }] }
    for (const [id, data] of [['track', { type: 'FeatureCollection', features: [line] } as any],
                              ['flown', { type: 'FeatureCollection', features: [flown] } as any],
                              ['pos', pos as any]]) {
      if (map.getSource(id)) (map.getSource(id) as any).setData(data)
      else map.addSource(id, { type: 'geojson', data })
    }
    for (const [id, layer] of [
      ['track-l', { id: 'track-l', type: 'line', source: 'track', paint: { 'line-color': '#5d675f', 'line-width': 2, 'line-dasharray': [2, 2] as any } }],
      ['flown-l', { id: 'flown-l', type: 'line', source: 'flown', paint: { 'line-color': '#0e6e5c', 'line-width': 3 } }],
      ['pos-c', { id: 'pos-c', type: 'circle', source: 'pos', paint: { 'circle-radius': 7, 'circle-color': '#c2410c', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } }]] as const) {
      if (!map.getLayer(id)) map.addLayer(layer)
    }
    const lons = rep.coords.map((c: any) => c[0]); const lats = rep.coords.map((c: any) => c[1])
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40, duration: 0 })
  }, [rep, ready, idx])
  useEffect(() => {
    if (!playing || !rep) return
    const t = setInterval(() => setIdx((i) => {
      if (i >= rep.coords.length - 1) { setPlaying(false); return i }
      return i + 1
    }), 220)
    return () => clearInterval(t)
  }, [playing, rep])

  const cur = rep?.fsm?.[Math.min(idx, (rep?.fsm?.length ?? 1) - 1)]
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
        <span className="microtype">historical track replay · playback scrubber · gap indicators · FSM badges</span>
        <select className="btn" value={vid} onChange={(e) => setVoy(e.target.value)}>
          {list.map((v) => <option key={v} value={v}>{v.slice(0, 22)}</option>)}
        </select>
      </div>
      <div ref={el} className="h-[320px]" />
      <div className="px-4 py-3" style={{ borderTop: '1px solid var(--color-rule)' }}>
        <div className="flex items-center gap-3">
          <button className="btn btn-acc" onClick={() => setPlaying(!playing)}>{playing ? 'PAUSE' : 'PLAY'}</button>
          <input type="range" min={0} max={(rep?.coords?.length ?? 1) - 1} value={idx}
            onChange={(e) => setIdx(+e.target.value)} className="flex-1" />
          <span className="mono text-xs text-dim">{idx + 1}/{rep?.coords?.length ?? 0}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5 items-center">
          {cur && <span className="chip chip-acc">FSM: {cur.state} · {cur.phase} · band {cur.sog_band}</span>}
          {rep?.gaps?.gaps?.slice(0, 3).map((g: any, i: number) => (
            <span key={i} className="chip chip-bad">AIS drop-out {g.gap_min} min</span>
          ))}
          {rep?.gaps && <span className="chip chip-ok">signal coverage {(rep.gaps.coverage * 100).toFixed(1)}%</span>}
        </div>
        {rep && (
          <EChart height={180} option={{
            grid: { left: 44, right: 12, top: 18, bottom: 26 },
            xAxis: { type: 'category', data: rep.sog.map((_: any, i: number) => i), ...AXIS },
            yAxis: { type: 'value', name: 'SOG kn', ...AXIS },
            series: [
              { type: 'line', data: rep.sog, symbol: 'none', lineStyle: { color: '#aab1a5', width: 1 } },
              { type: 'line', data: rep.sog_smoothed, symbol: 'none', lineStyle: { color: '#0e6e5c', width: 2 },
                areaStyle: { color: 'rgba(14,110,92,0.08)' } },
            ],
            tooltip: { trigger: 'axis' },
          }} />
        )}
        {rep && (
          <EChart height={150} option={{
            grid: { left: 44, right: 12, top: 18, bottom: 26 },
            xAxis: { type: 'category', data: rep.fuel_series_t_day.map((_: any, i: number) => i), ...AXIS },
            yAxis: { type: 'value', name: 'fuel t/day', ...AXIS },
            series: [{ type: 'line', data: rep.fuel_series_t_day, symbol: 'none',
                       lineStyle: { color: '#a86a00', width: 2 } }],
            tooltip: { trigger: 'axis' },
          }} />
        )}
      </div>
    </div>
  )
}

/* ── wave field + wind barbs ── */
function WaveField() {
  const [d, setD] = useState<any>(null)
  useEffect(() => { fetch(API + '/v2/live/wavefield?lat=59.5&lon=21&step=1&n=4').then((r) => r.json()).then(setD) }, [])
  const grid = d?.grid ?? []
  return (
    <div className="panel p-4">
      <div className="microtype" style={{ borderBottom: '1px solid var(--color-rule)', paddingBottom: 8 }}>
        wave height gradient field + wind barbs · Open-Meteo marine grid (Baltic)
      </div>
      <EChart height={230} option={grid.length ? {
        grid: { left: 50, right: 16, top: 20, bottom: 30 },
        xAxis: { type: 'value', name: 'lon +', min: 0, max: 3, ...AXIS },
        yAxis: { type: 'value', name: 'lat +', min: 0, max: 3, ...AXIS },
        visualMap: { min: 0, max: Math.max(1.5, ...grid.map((c: any) => c.wave_height ?? 0)),
                     calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
                     inRange: { color: ['#cfe3de', '#0e6e5c'] }, textStyle: { color: '#5d675f' } },
        series: [
          { type: 'heatmap', data: grid.map((c: any) => [c.lng - 21, c.lat - 59.5, c.wave_height ?? 0]),
            pointSize: 18, blurSize: 24 },
          { type: 'scatter', symbol: 'triangle', symbolSize: 10, symbolRotate: grid.map((c: any) => (c.wind_dir_deg ?? 0)),
            data: grid.map((c: any) => [c.lng - 21, c.lat - 59.5]),
            itemStyle: { color: '#17201b' }, z: 5 },
        ],
        tooltip: { formatter: (p: any) => `cell ${p.data[0].toFixed(0)},${p.data[1].toFixed(0)}` },
      } : {}} />
      <div className="mono mt-1 text-[11px] text-dim">triangles = wind direction barbs at cell centers; color field = significant wave height</div>
    </div>
  )
}

/* ── bathymetric contour slice ── */
function ContourSlice() {
  const [d, setD] = useState<any>(null)
  useEffect(() => { fetch(API + '/v2/live/bathymetry?lat=59.9&lon=24.9').then((r) => r.json()).then(setD) }, [])
  const pts = d?.profile ?? []
  return (
    <div className="panel p-4">
      <div className="microtype" style={{ borderBottom: '1px solid var(--color-rule)', paddingBottom: 8 }}>
        bathymetric cross-section · EMODnet DTM via OpenTopoData (Gulf of Finland transect)
      </div>
      <EChart height={200} option={pts.length ? {
        grid: { left: 50, right: 12, top: 18, bottom: 26 },
        xAxis: { type: 'category', data: pts.map((_: any, i: number) => i), ...AXIS },
        yAxis: { type: 'value', inverse: true, name: 'depth m', ...AXIS },
        series: [{ type: 'line', data: pts.map((p: any) => p.depth_m), smooth: true, showSymbol: false,
                   lineStyle: { color: '#0d7d8c', width: 2 }, areaStyle: { color: 'rgba(13,125,140,0.12)' } }],
        tooltip: { trigger: 'axis', formatter: (ps: any) => ps.map((p: any) =>
          `${pts[p.dataIndex].lat.toFixed(2)}, ${pts[p.dataIndex].lon.toFixed(2)} → ${p.value} m`).join('<br/>') },
      } : {}} />
    </div>
  )
}

export default function Analytics() {
  const [res, setRes] = useState(4)
  const [hexes, setHexes] = useState<any[]>([])
  useEffect(() => { j('/v2/analytics/h3?resolution=' + res).then((d: any) => d && setHexes(d.hexes)) }, [res])

  return (
    <main className="mx-auto max-w-7xl px-5 pt-20">
      <div className="flex flex-wrap items-end justify-between gap-4 py-5">
        <div>
          <div className="microtype">historical analytics · H3 · HDBSCAN · networkx · ITTC/Townsin-Glover</div>
          <h1 className="mt-1 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">Analytics workbench</h1>
        </div>
        <div className="flex gap-2">
          {[3, 4, 5].map((r) => (
            <button key={r} onClick={() => setRes(r)} className={`btn ${res === r ? 'btn-acc' : ''}`}>H3 r{r}</button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="panel">
          <div className="microtype px-4 py-2.5 hairline-b">H3 hexagon density · July 2024 samples</div>
          <HexHeat data={hexes} />
        </div>
        <div className="grid gap-4">
          <RouteOptimizer />
          <AnomalyGauge />
          <BioChips />
        </div>
      </div>

      <div className="mt-4 grid gap-4">
        <FuelPanel />
        <Anchorages />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <DepthProfile />
        <HmmPanel />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <WaveField />
        <ContourSlice />
      </div>

      <div className="mt-4">
        <ReplayPanel />
      </div>

      <Footer />
    </main>
  )
}
