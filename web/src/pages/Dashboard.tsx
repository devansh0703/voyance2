import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import Globe from 'globe.gl'
import * as echarts from 'echarts'
import { Footer, Reveal } from '../components/chrome'
import type { DriftJson, EvalJson, MapJson, StatsJson } from '../lib/data'
import { useArtifact } from '../lib/data'
import 'maplibre-gl/dist/maplibre-gl.css'

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

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {},
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#071523' } }],
      },
      center: [-95, 32],
      zoom: 3.4,
      attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => { mapRef.current = map; setMapReady(true) })
    return () => { map.remove(); mapRef.current = null; setMapReady(false) }
  }, [])

  const v = mapJson?.voyages?.[sel]

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
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        paint: {
          'line-color': '#29e6d2',
          'line-width': 3,
          'line-opacity': 0.9,
        },
      })
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
        paint: { 'circle-radius': 6, 'circle-color': '#29e6d2' },
      })
      map.addLayer({
        id: 'port-arr', type: 'circle', source: 'ports',
        filter: ['==', 'kind', 'arr'],
        paint: { 'circle-radius': 6, 'circle-color': '#ff7a59' },
      })
    }
    const lons = v.coords.map((c) => c[0]); const lats = v.coords.map((c) => c[1])
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 60, duration: 800 },
    )
  }, [v, mapReady])

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div ref={el} className="h-[520px] overflow-hidden rounded-2xl border border-mist/10" />
      <div className="flex flex-col gap-2">
        {!mapJson ? <NotReady what="Showcase voyages" /> :
          mapJson.voyages.slice(0, 12).map((vo, i) => (
            <button
              key={vo.voyage_id}
              onClick={() => setSel(i)}
              className={`bento px-4 py-3 text-left text-sm ${i === sel ? 'border-bio/50' : ''}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{vo.dep_port} → {vo.arr_port}</span>
                <span className={`font-[family-name:var(--font-mono)] text-xs ${(vo.err_pct ?? 0) > 0.2 ? 'text-signal' : 'text-bio'}`}>
                  {vo.duration_h.toFixed(1)} h
                </span>
              </div>
              <div className="mt-1 text-xs text-mist">
                {vo.vessel_type_group} · mean err {vo.err_pct == null ? '—' : `${(vo.err_pct * 100).toFixed(1)}%`}
              </div>
            </button>
          ))}
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
      itemStyle: { color, borderRadius: [6, 6, 0, 0] },
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
  const alerts = drift.weeks.filter((w) => w.alert)
  return (
    <div className="space-y-4">
      {alerts.length > 0 && (
        <div className="rounded-2xl border border-signal/40 bg-signal/10 p-4 text-sm">
          <span className="font-semibold text-signal">Drift alerts:</span>{' '}
          {alerts.map((a) => `week of ${a.week} (MAE ×${a.mae_ratio.toFixed(2)})`).join(' · ')}
        </div>
      )}
      <div className="bento p-4">
        <EChart
          option={{
            title: { text: `Weekly MAE ratio vs ${drift.baseline} baseline (monitor: ${drift.monitor})`, textStyle: { color: '#e8f4f8', fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            grid: { left: 50, right: 20, bottom: 50, top: 40 },
            xAxis: { type: 'category' as const, data: drift.weeks.map((w) => w.week), axisLabel: { fontSize: 10 } },
            yAxis: { type: 'value' as const, name: 'MAE ratio' },
            series: [
              { type: 'line' as const, data: drift.weeks.map(() => 1), lineStyle: { color: 'rgba(159,194,209,0.4)', type: 'dashed' }, symbol: 'none', name: 'baseline' },
              {
                type: 'line' as const, data: drift.weeks.map((w) => w.mae_ratio), smooth: true,
                lineStyle: { color: '#ffd166', width: 2 }, itemStyle: { color: '#ffd166' }, name: 'monitor',
              },
            ],
          }}
        />
      </div>
      <div className="glass overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-mist/80">
            <tr className="border-b border-mist/10">
              <th className="px-4 py-3 font-medium">Week</th>
              <th className="px-4 py-3 font-medium">MAE (h)</th>
              <th className="px-4 py-3 font-medium">Ratio vs baseline</th>
              <th className="px-4 py-3 font-medium">Drifted features (PSI&gt;0.2)</th>
              <th className="px-4 py-3 font-medium">Alert</th>
            </tr>
          </thead>
          <tbody>
            {drift.weeks.map((w) => (
              <tr key={w.week} className="border-b border-mist/5">
                <td className="px-4 py-3 font-mono text-xs">{w.week}</td>
                <td className="px-4 py-3">{w.mae_h.toFixed(2)}</td>
                <td className="px-4 py-3">{w.mae_ratio.toFixed(2)}</td>
                <td className="px-4 py-3 text-mist">
                  {w.drifted_features.length
                    ? w.drifted_features.map((f) => `${f.feature} (${f.psi.toFixed(2)})`).join(', ')
                    : '—'}
                </td>
                <td className="px-4 py-3">
                  {w.alert ? <span className="rounded bg-signal/20 px-2 py-0.5 text-xs text-signal">ALERT</span>
                    : <span className="rounded bg-bio/10 px-2 py-0.5 text-xs text-bio">ok</span>}
                </td>
              </tr>
            ))}
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
