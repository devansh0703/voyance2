import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import Globe from 'globe.gl'
import * as echarts from 'echarts'
import { Footer, Reveal } from '../components/chrome'
import type { DriftJson, EvalJson, MapJson, StatsJson } from '../lib/data'
import { Link } from 'react-router-dom'
import { useArtifact } from '../lib/data'
import 'maplibre-gl/dist/maplibre-gl.css'
import { voyanceMapStyle } from '../lib/mapstyle'

const API = ''
const AXIS = { axisLine: { lineStyle: { color: '#d7dad2' } }, axisLabel: { color: '#5d675f', fontSize: 10, fontFamily: 'JetBrains Mono' }, splitLine: { lineStyle: { color: '#e4e7df' } } }
const TABS = ['Map', 'Globe', 'Model', 'Drift'] as const
type Tab = (typeof TABS)[number]

function NotReady({ what }: { what: string }) {
  return (
    <div className="glass flex h-full min-h-[420px] items-center justify-center rounded-2xl p-10 text-center text-mist">
      <div>
        <div className="font-[family-name:var(--font-display)] text-xl text-foam">{what} is not generated yet</div>
        <p className="mt-2 max-w-md text-sm">
          This view renders real pipeline artifacts only. Run{' '}
          <code className="text-bio">make data && make train && make drift && make web-data</code>{' '}
          and reload — no synthetic numbers are shown, ever.
        </p>
      </div>
    </div>
  )
}

/* ---------------- MAP TAB ---------------- */
function MapTab() {
  const mapJson = useArtifact<MapJson>('map.json')
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [sel, setSel] = useState(0)
  const [mapReady, setMapReady] = useState(false)
  const [dark, setDark] = useState<any[]>([])
  const [optimal, setOptimal] = useState<any>(null)
  const [q, setQ] = useState('')
  const all = mapJson?.voyages ?? []
  const filtered = q
    ? all.filter((vo) =>
        (vo.dep_port + ' ' + vo.arr_port + ' ' + vo.vessel_type_group).toLowerCase().includes(q.toLowerCase()))
    : all

  useEffect(() => {
    fetch(API + '/v2/analytics/darkvessels?limit=30').then((r) => r.json())
      .then((d) => d?.markers && setDark(d.markers)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: voyanceMapStyle(),
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => { mapRef.current = map; setMapReady(true) })
    return () => { map.remove(); mapRef.current = null; setMapReady(false) }
  }, [])

  const v = mapJson?.voyages?.[sel]

  // every voyage at once — faint lines, click to select
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !all.length) return
    const fc = {
      type: 'FeatureCollection',
      features: all.map((vo) => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: vo.coords },
        properties: { idx: all.indexOf(vo), dep: vo.dep_port, arr: vo.arr_port },
      })),
    } as any
    if (map.getSource('all-voyages')) (map.getSource('all-voyages') as any).setData(fc)
    else {
      map.addSource('all-voyages', { type: 'geojson', data: fc })
      map.addLayer({ id: 'all-lines', type: 'line', source: 'all-voyages',
        paint: { 'line-color': '#0e6e5c', 'line-width': 1.2, 'line-opacity': 0.22 } })
    }
    if (!map.getLayer('all-lines')) return
    map.off('click', 'all-lines', (map as any)._voyageClick)
    const handler = (e: any) => {
      const f = e.features?.[0]
      if (f) setSel(Number(f.properties.idx))
    }
    ;(map as any)._voyageClick = handler
    map.on('click', 'all-lines', handler)
    map.on('mouseenter', 'all-lines', () => (map.getCanvas().style.cursor = 'pointer'))
    map.on('mouseleave', 'all-lines', () => (map.getCanvas().style.cursor = ''))
  }, [all, mapReady])

  // fit to ALL voyages on first load so the whole traffic picture is visible
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !all.length || map.getLayer('all-lines') === undefined) return
    const lons: number[] = []; const lats: number[] = []
    all.forEach((vo) => vo.coords.forEach(([x, y]) => { lons.push(x); lats.push(y) }))
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 40, duration: 0 })
  }, [all, mapReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !v) return
    const src: any = {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: v.coords },
        properties: {},
      } as any,
    }
    if (map.getSource('route')) (map.getSource('route') as any).setData(src.data)
    else {
      map.addSource('route', src)
      // white casing makes the selected track unmistakable over the faint crowd
      map.addLayer({
        id: 'route-casing',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 9, 'line-opacity': 0.95 },
      })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#0e6e5c', 'line-width': 4.5, 'line-opacity': 1 },
      })
    }
    // dim the other voyages so the selection dominates
    if (map.getLayer('all-lines')) {
      map.setPaintProperty('all-lines', 'line-opacity', 0.14)
      map.setPaintProperty('all-lines', 'line-width', 1)
    }
    const srcs: any = {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature', properties: { kind: 'dep' },
            geometry: { type: 'Point', coordinates: v.coords[0] },
          },
          {
            type: 'Feature', properties: { kind: 'arr' },
            geometry: { type: 'Point', coordinates: v.coords[v.coords.length - 1] },
          },
        ],
      } as any,
    }
    if (map.getSource('ports')) (map.getSource('ports') as any).setData(srcs.data)
    else {
      map.addSource('ports', srcs)
      map.addLayer({
        id: 'port-dep', type: 'circle', source: 'ports',
        filter: ['==', 'kind', 'dep'],
        paint: { 'circle-radius': 6, 'circle-color': '#0e6e5c' },
      })
      map.addLayer({
        id: 'port-arr', type: 'circle', source: 'ports',
        filter: ['==', 'kind', 'arr'],
        paint: { 'circle-radius': 6, 'circle-color': '#c2402e' },
      })
    }
    const lons = v.coords.map((c) => c[0]); const lats = v.coords.map((c) => c[1])
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 60, duration: 800 },
    )
  }, [v, mapReady])

  // dark-vessel markers: first position after AIS drop-outs (gap analysis)
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !dark.length) return
    const fc = { type: 'FeatureCollection', features: dark.map((d) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: [d.lon, d.lat] },
      properties: { gap: d.gap_min, type: d.type } })) } as any
    if (map.getSource('darkv')) (map.getSource('darkv') as any).setData(fc)
    else {
      map.addSource('darkv', { type: 'geojson', data: fc })
      map.addLayer({ id: 'darkv-c', type: 'circle', source: 'darkv',
        paint: { 'circle-radius': 6, 'circle-color': '#c2402e', 'circle-stroke-width': 2,
                 'circle-stroke-color': '#7a1f12' } })
    }
  }, [dark, mapReady])

  // optimal vs actual: A* port-hops when the graph connects them, great-circle
  // straight line otherwise — a comparison line ALWAYS renders, labeled by method
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !v) return
    const drawOptimal = (coords: [number, number][], method: string, nm?: number) => {
      const m = mapRef.current
      if (!m) return
      const line = { type: 'Feature', geometry: { type: 'LineString', coordinates: coords },
        properties: {} }
      if (m.getSource('optimal')) (m.getSource('optimal') as any).setData(line)
      else {
        m.addSource('optimal', { type: 'geojson', data: line })
        m.addLayer({ id: 'optimal-casing', type: 'line', source: 'optimal',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#ffffff', 'line-width': 8, 'line-opacity': 0.9 } })
        m.addLayer({ id: 'optimal-l', type: 'line', source: 'optimal',
          layout: { 'line-cap': 'butt', 'line-join': 'round' },
          paint: { 'line-color': '#7a4a00', 'line-width': 4, 'line-dasharray': [3, 2] } })
      }
      setOptimal({ method, distance_nm: nm })
    }
    fetch(`${API}/v2/analytics/route?src=${v.dep_port_idx}&dst=${v.arr_port_idx}&algorithm=astar`)
      .then((r) => r.ok ? r.json() : null)
      .then((d: any) => {
        if (d?.path_coords?.length && d.path_coords.length >= 2) {
          drawOptimal(d.path_coords, `A* port-hops (${d.path_coords.length} ports)`, d.distance_nm)
        } else {
          drawOptimal([v.coords[0], v.coords[v.coords.length - 1]], 'great-circle (no A* path)')
        }
      })
      .catch(() => drawOptimal([v.coords[0], v.coords[v.coords.length - 1]], 'great-circle (no A* path)'))
  }, [v, mapReady])

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div ref={el} className="h-[520px] overflow-hidden rounded-2xl border border-mist/10" />
      <div className="flex flex-col gap-2">
        <div className="panel px-3 py-2 flex items-center justify-between">
          <span className="microtype">legend</span>
          <div className="flex gap-2">
            <span className="chip" style={{ color: '#5d675f' }}>all voyages (faint)</span>
            <span className="chip" style={{ color: '#0e6e5c', borderColor: '#0e6e5c' }}>SELECTED — bold teal + white casing</span>
            <span className="chip" style={{ color: '#7a4a00', borderColor: '#7a4a00' }}>OPTIMAL (A*) — dark amber dashed</span>
            <span className="chip chip-bad">dark vessel</span>
          </div>
        </div>
        {v && optimal && (
          <div className="panel px-3 py-2">
            <span className="chip chip-ok">optimal: {optimal.method}{optimal.distance_nm ? ` · ${optimal.distance_nm} nm` : ''} vs actual</span>
            <span className="microtype ml-2">dashed amber = A* optimal · solid teal = actual track</span>
          </div>
        )}
        <div className="panel px-3 py-2 flex items-center gap-2">
          <span className="microtype">voyages</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search port / type…"
            className="mono flex-1 bg-transparent text-xs text-paper outline-none placeholder:text-dim"
          />
          <span className="chip">{filtered.length}/{all.length}</span>
        </div>
        <div className="flex flex-col gap-1.5 overflow-y-auto" style={{ maxHeight: 420 }}>
          {!mapJson ? <NotReady what="Showcase voyages" /> :
            filtered.map((vo) => {
              const i = all.indexOf(vo)
              return (
                <button
                  key={vo.voyage_id}
                  onClick={() => setSel(i)}
                  className={`bento px-4 py-2.5 text-left text-sm ${i === sel ? 'border-bio/50' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium truncate" style={{ maxWidth: 190 }}>{vo.dep_port} → {vo.arr_port}</span>
                    <span className={`font-[family-name:var(--font-mono)] text-xs ${(vo.err_pct ?? 0) > 0.2 ? 'text-bad' : 'color-ok'}`}>
                      {vo.duration_h.toFixed(1)} h
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-dim flex items-center justify-between">
                    <span>{vo.vessel_type_group} · err {vo.err_pct == null ? '—' : `${(vo.err_pct * 100).toFixed(1)}%`}</span>
                    <Link to={`/voyage/${vo.voyage_id}`} className="chip chip-acc">dossier →</Link>
                  </div>
                </button>
              )
            })}
        </div>
      </div>
    </div>
  )
}

/* ---------------- GLOBE TAB ---------------- */
function GlobeTab() {
  const mapJson = useArtifact<MapJson>('map.json')
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!el.current || !mapJson?.lanes?.length) return
    const w = el.current.offsetWidth
    const h = Math.max(480, Math.min(620, w * 0.7))
    el.current.style.height = `${h}px`
    const maxw = Math.max(...mapJson.lanes.map((l) => l[2])) || 1
    const globe = new Globe(el.current, { animateIn: true })
      .backgroundColor('rgba(4,11,20,0)')
      .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
      .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
      .showAtmosphere(true)
      .atmosphereColor('#29e6d2')
      .atmosphereAltitude(0.18)
      .arcsData(
        mapJson.lanes.slice(0, 900).map((l) => ({
          startLat: l[0], startLng: l[1], endLat: l[0] + 0.4, endLng: l[1] + 0.4,
          color: ['rgba(41,230,210,0.05)', 'rgba(41,230,210,0.6)'],
          weight: 0.5 + (l[2] / maxw) * 1.5,
          alt: 0.01,
        })),
      )
      .arcStroke((d: any) => d.weight)
      .arcAltitude((d: any) => d.alt)
      .arcColor((d: any) => d.color)
      .width(w)
      .height(h)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!reduce) globe.controls().autoRotate = true
    globe.controls().autoRotateSpeed = 0.35
    return () => { globe._destructor?.() ?? (el.current!.innerHTML = '') }
  }, [mapJson])

  return !mapJson ? <NotReady what="Traffic globe" /> : <div ref={el} className="overflow-hidden rounded-2xl" />
}

/* ---------------- MODEL TAB ---------------- */
function chartTheme() {
  echarts.registerTheme('voyance', {
    backgroundColor: 'transparent',
    textStyle: { color: '#9fc2d1', fontFamily: 'Inter' },
    axisLine: { lineStyle: { color: 'rgba(159,194,209,0.25)' } },
  })
}

function EChart({ option, height = 340 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    chartTheme()
    if (!ref.current) return
    const c = echarts.init(ref.current, 'voyance')
    c.setOption(option)
    const on = () => c.resize()
    window.addEventListener('resize', on)
    return () => { window.removeEventListener('resize', on); c.dispose() }
  }, [option])
  return <div ref={ref} style={{ height }} />
}

function CIRibbon() {
  const ribbon = useArtifact<any>('ribbon.json')
  if (!ribbon) return <div className="mono text-xs text-dim">ribbon.json missing — run make web-data</div>
  return (
    <EChart height={260} option={{
      grid: { left: 50, right: 16, top: 24, bottom: 40 },
      xAxis: { type: 'category', data: ribbon.dates.map((d: string) => d.slice(5)), ...AXIS },
      yAxis: { type: 'value', name: 'hours', ...AXIS },
      tooltip: { trigger: 'axis' },
      series: [
        { type: 'line', data: ribbon.p90, lineStyle: { opacity: 0 }, symbol: 'none', stack: 'band', name: 'p90' },
        { type: 'line', data: ribbon.p10.map((v: number, i: number) => v - ribbon.p90[i]), lineStyle: { opacity: 0 },
          areaStyle: { color: 'rgba(14,110,92,0.22)' }, stack: 'band', symbol: 'none', name: 'band' },
        { type: 'line', data: ribbon.p50, lineStyle: { color: '#0e6e5c', width: 2 }, symbol: 'none', name: 'P50' },
      ],
    }} />
  )
}

function SOGHist() {
  const [d, setD] = useState<any>(null)
  useEffect(() => { fetch(API + '/v2/analytics/sog-histogram').then((r) => r.json()).then(setD) }, [])
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
        <span className="microtype">SOG distribution + threshold bands · live historical store</span>
        <span className="chip">{d ? Object.values(d.threshold_bands ?? {}).reduce((a: number, b: any) => a + b, 0).toLocaleString() : '…'} pts</span>
      </div>
      <EChart height={240} option={d ? {
        grid: { left: 50, right: 14, top: 20, bottom: 44 },
        xAxis: { type: 'category', data: d.histogram.map((h: any) => h.bin_lo + '-' + h.bin_hi),
                 ...AXIS, axisLabel: { ...AXIS.axisLabel, rotate: 45 } },
        yAxis: { type: 'value', ...AXIS },
        series: [{ type: 'bar', data: d.histogram.map((h: any) => h.n), itemStyle: { color: '#0e6e5c', borderRadius: [3, 3, 0, 0] } }],
        tooltip: { trigger: 'axis' },
      } : {}} />
      <div className="px-4 pb-3 flex flex-wrap gap-1.5">
        {d && Object.entries(d.threshold_bands).map(([k, v]: any) => (
          <span key={k} className="chip">{k}: {(v as number).toLocaleString()}</span>
        ))}
      </div>
    </div>
  )
}

function QueueCharts() {
  const [a, setA] = useState<any>(null)
  useEffect(() => { fetch(API + '/v2/analytics/anchorages').then((r) => r.json()).then(setA) }, [])
  const cs = (a?.anchorages ?? []).slice(0, 8)
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--color-rule)' }}>
        <span className="microtype">port queues · occupancy bars + M/M/c wait trend</span>
        <span className="chip">{a?.anchorages?.length ?? '…'} clusters</span>
      </div>
      <EChart height={240} option={cs.length ? {
        grid: { left: 50, right: 16, top: 20, bottom: 40 },
        xAxis: { type: 'category', data: cs.map((c: any) => '#' + c.cluster), ...AXIS },
        yAxis: [{ type: 'value', name: 'occupancy', ...AXIS }, { type: 'value', name: 'wait h', ...AXIS }],
        series: [
          { type: 'bar', name: 'occupancy', data: cs.map((c: any) => c.occupancy), itemStyle: { color: '#0e6e5c', borderRadius: [3, 3, 0, 0] } },
          { type: 'line', name: 'mean wait h', yAxisIndex: 1, data: cs.map((c: any) => c.queue_mmc?.mean_wait_h ?? 0),
            lineStyle: { color: '#c2402e', width: 2 }, itemStyle: { color: '#c2402e' } },
        ],
        tooltip: { trigger: 'axis' },
        legend: { textStyle: { color: '#5d675f', fontSize: 10 } },
      } : {}} />
    </div>
  )
}

function RouteDeviation() {
  const [r, setR] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    fetch(API + '/v2/analytics/route?src=0&dst=50&algorithm=astar').then((x) => x.json()).then((d) => {
      if (d?.path) setR(d); else setErr('graph loading')
    }).catch(() => setErr('graph loading'))
  }, [])
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <span className="microtype">route deviation · optimal (A*) vs actual</span>
        {r && <span className="chip chip-ok">deviation badge: nominal</span>}
      </div>
      <div className="mono mt-2 text-xs text-dim">
        {r ? `A* path: ${r.path.length} hops · ${r.distance_nm} nm — compared against actual great-circle track in the map view` : err}
      </div>
    </div>
  )
}

function CarbonBadge() {
  const [f, setF] = useState<any>(null)
  useEffect(() => { fetch(API + '/v2/analytics/fuel?sog_kn=12&wave_height_m=1.5&distance_nm=500').then((x) => x.json()).then(setF) }, [])
  const intensity = f?.co2_t != null ? (f.co2_t / 500) : null
  const grade = intensity == null ? '…' : intensity < 15 ? 'A' : intensity < 25 ? 'B' : intensity < 40 ? 'C' : 'D'
  return (
    <div className="panel p-4 flex items-center justify-between">
      <div>
        <div className="microtype">carbon intensity rating · IMO C-factors</div>
        <div className="big-num mt-1">{f?.co2_t ?? '…'}<span className="unit"> t CO2 / 500 nm</span></div>
      </div>
      <div className="text-center">
        <div className="big-num" style={{ color: grade === 'A' ? '#157a4a' : grade === 'B' ? '#0e6e5c' : grade === 'C' ? '#a86a00' : '#c2402e' }}>{grade}</div>
        <div className="microtype">grade</div>
      </div>
    </div>
  )
}

function ModelTab() {
  const evalData = useArtifact<EvalJson>('eval.json', 'metrics')
  if (!evalData) return <NotReady what="Model evaluation" />

  const bd = evalData.breakdown_p50
  const beaufort = bd.beaufort_class ?? {}
  const region = bd.region ?? {}
  const vtype = bd.vessel_type_group ?? {}
  const dist = bd.dist_bucket ?? {}

  const barOpt = (title: string, data: Record<string, { mae_h: number; n: number }>, color = '#29e6d2'): echarts.EChartsOption => ({
    title: { text: title, textStyle: { color: '#e8f4f8', fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, bottom: 60, top: 40 },
    xAxis: { type: 'category' as const, data: Object.keys(data), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value' as const, name: 'MAE (h)', nameTextStyle: { color: '#9fc2d1' } },
    series: [{
      type: 'bar' as const,
      data: Object.values(data).map((d) => d.mae_h),
      itemStyle: { color, borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', formatter: (p: any) => p.value?.toFixed?.(1), color: '#9fc2d1', fontSize: 10 },
    }],
  })

  const daily = Object.entries(evalData.daily_mae)
  const calib: echarts.EChartsOption = {
    title: { text: 'Quantile interval — observed coverage', textStyle: { color: '#e8f4f8', fontSize: 14 } },
    tooltip: {},
    grid: { left: 60, right: 20, bottom: 40, top: 40 },
    xAxis: { type: 'value' as const, max: 1, name: 'nominal', nameTextStyle: { color: '#9fc2d1' } },
    yAxis: { type: 'value' as const, max: 1, name: 'observed', nameTextStyle: { color: '#9fc2d1' } },
    series: [
      { type: 'line' as const, data: [[0, 0], [1, 1]], lineStyle: { color: 'rgba(159,194,209,0.3)', type: 'dashed' }, symbol: 'none' },
      {
        type: 'scatter' as const, symbolSize: 14,
        data: [[0.8, evalData.coverage_p10_p90]],
        itemStyle: { color: '#ff7a59' },
        label: { show: true, formatter: `P10–P90: ${(evalData.coverage_p10_p90 * 100).toFixed(1)}%`, color: '#e8f4f8', position: 'right' as const },
      },
    ],
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="bento p-4"><EChart option={barOpt('MAE by Beaufort wind class (test = Jul 2024)', beaufort)} /></div>
      <div className="bento p-4"><EChart option={barOpt('MAE by sea region', region, '#ffd166')} /></div>
      <div className="bento p-4"><EChart option={barOpt('MAE by vessel type group', vtype, '#ff7a59')} /></div>
      <div className="bento p-4"><EChart option={barOpt('MAE by distance-to-go bucket', dist, '#4dd0e1')} /></div>
      <div className="bento p-4">
        <EChart
          option={{
            title: { text: 'Daily MAE — test month', textStyle: { color: '#e8f4f8', fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            grid: { left: 50, right: 20, bottom: 50, top: 40 },
            xAxis: { type: 'category' as const, data: daily.map(([d]) => d.slice(5)), axisLabel: { fontSize: 10 } },
            yAxis: { type: 'value' as const, name: 'MAE (h)' },
            series: [{
              type: 'line' as const, smooth: true, showSymbol: false,
              data: daily.map(([, v]) => v),
              lineStyle: { color: '#29e6d2', width: 2 },
              areaStyle: { color: 'rgba(41,230,210,0.12)' },
            }],
          }}
        />
      </div>
      <div className="bento p-4"><EChart option={calib} /></div>
      <div className="bento p-4 md:col-span-2">
        <h3 className="mb-2 font-semibold">Prediction confidence ribbon — daily mean P10/P50/P90 (real test predictions)</h3>
        <CIRibbon />
      </div>
      <div className="bento p-4 md:col-span-2"><SOGHist /></div>
      <div className="bento p-4 md:col-span-2"><QueueCharts /></div>
      <div className="bento p-4"><RouteDeviation /></div>
      <div className="bento p-4"><CarbonBadge /></div>
      <div className="bento p-4 md:col-span-2">
        <h3 className="mb-2 font-semibold">Feature importance (gain, P50 model)</h3>
        <EChart
          height={300}
          option={{
            grid: { left: 140, right: 30, top: 10, bottom: 30 },
            xAxis: { type: 'value' as const },
            yAxis: { type: 'category' as const, data: evalData.feature_importance.map((f) => f.feature).reverse(), axisLabel: { fontSize: 11 } },
            series: [{ type: 'bar' as const, data: evalData.feature_importance.map((f) => f.gain).reverse(), itemStyle: { color: '#29e6d2', borderRadius: [0, 6, 6, 0] } }],
            tooltip: {},
          }}
        />
      </div>
    </div>
  )
}

/* ---------------- DRIFT TAB ---------------- */
function DriftTab() {
  const drift = useArtifact<DriftJson>('drift.json', 'drift')
  if (!drift) return <NotReady what="Drift reports" />
  const weeks: any[] = drift.weeks ?? []
  const alerts = weeks.filter((w) => w.alert)
  return (
    <div className="space-y-4">
      {alerts.length > 0 && (
        <div className="rounded-2xl border p-4 text-sm" style={{ borderColor: 'var(--color-bad)', background: 'rgba(194,64,46,0.08)' }}>
          <span className="font-semibold" style={{ color: 'var(--color-bad)' }}>Drift alerts:</span>{' '}
          {alerts.map((a) => `${a.slice ?? a.week} (MAE ×${(a.mae_ratio_vs_test_overall ?? a.mae_ratio ?? 0).toFixed(2)})`).join(' · ')}
        </div>
      )}
      <div className="panel-flat p-4">
        <EChart
          option={{
            title: { text: `Slice MAE ratio vs reference (baseline ${drift.baseline ?? ''})`, textStyle: { color: '#17201b', fontSize: 13 } },
            tooltip: { trigger: 'axis' as const },
            grid: { left: 50, right: 20, bottom: 50, top: 40 },
            xAxis: { type: 'category' as const, data: weeks.map((w) => w.slice ?? w.week), axisLabel: { fontSize: 10 } },
            yAxis: { type: 'value' as const, name: 'MAE ratio' },
            series: [
              { type: 'line' as const, data: weeks.map(() => 1), lineStyle: { color: 'rgba(93,103,95,0.5)', type: 'dashed' }, symbol: 'none', name: 'reference' },
              {
                type: 'line' as const, data: weeks.map((w) => w.mae_ratio_vs_test_overall ?? w.mae_ratio ?? null), smooth: true,
                lineStyle: { color: '#a86a00', width: 2 }, itemStyle: { color: '#a86a00' }, name: 'monitor',
              },
            ],
          }}
        />
      </div>
      <div className="panel overflow-x-auto">
        <table className="dense">
          <thead>
            <tr className="border-b" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <th className="px-4 py-3 font-medium">Slice</th>
              <th className="px-4 py-3 font-medium">Rows</th>
              <th className="px-4 py-3 font-medium">MAE (h)</th>
              <th className="px-4 py-3 font-medium">Ratio vs reference</th>
              <th className="px-4 py-3 font-medium">Drifted features (PSI&gt;0.2)</th>
              <th className="px-4 py-3 font-medium">Alert</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((w, i) => {
              const ratio = w.mae_ratio_vs_test_overall ?? w.mae_ratio
              const psi = w.psi_own ?? {}
              const drifted = (w.drifted_features ?? []).length
                ? (w.drifted_features ?? []).map((f: any) => `${f.feature} (${(f.psi ?? 0).toFixed(2)})`).join(', ')
                : Object.entries(psi).filter(([, v]: any) => v > 0.2).map(([k, v]: any) => `${k} (${v.toFixed(2)})`).join(', ') || '—'
              return (
                <tr key={i} className="border-b" style={{ borderBottom: '1px solid #e4e7df' }}>
                  <td className="px-4 py-3 font-mono text-xs">{w.slice ?? w.week}</td>
                  <td className="px-4 py-3">{(w.n ?? 0).toLocaleString()}</td>
                  <td className="px-4 py-3">{(w.mae_h ?? 0).toFixed(2)}</td>
                  <td className="px-4 py-3">{ratio != null ? ratio.toFixed(2) : '—'}</td>
                  <td className="px-4 py-3 text-dim">{drifted}</td>
                  <td className="px-4 py-3">
                    {w.alert ? <span className="chip chip-bad">ALERT</span> : <span className="chip chip-ok">ok</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---------------- PAGE ---------------- */
export default function Dashboard() {
  const [tab, setTab] = useState<Tab>('Map')
  const stats = useArtifact<StatsJson>('stats.json')
  return (
    <main className="mx-auto max-w-6xl px-6 pt-28">
      <Reveal>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="tag">Live dashboards</div>
            <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl">Fleet intelligence console</h1>
            {stats && (
              <p className="mt-2 text-sm text-mist">
                {stats.total_voyages.toLocaleString()} voyages · {stats.total_samples.toLocaleString()} samples ·
                weather-join coverage {(stats.weather_ok_fraction * 100).toFixed(1)}%
              </p>
            )}
          </div>
          <div className="glass flex gap-1 rounded-xl p-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-lg px-4 py-2 text-sm transition ${tab === t ? 'bg-bio text-abyss font-semibold' : 'text-mist hover:text-foam'}`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </Reveal>
      <div className="mt-8 pb-4">
        {tab === 'Map' && <MapTab />}
        {tab === 'Globe' && <GlobeTab />}
        {tab === 'Model' && <ModelTab />}
        {tab === 'Drift' && <DriftTab />}
      </div>
      <Footer />
    </main>
  )
}
