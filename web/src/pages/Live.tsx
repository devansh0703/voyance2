import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import { Footer } from '../components/chrome'
import 'maplibre-gl/dist/maplibre-gl.css'

const API = ''

async function j<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(API + url)
    if (!r.ok) return null
    return await r.json()
  } catch {
    return null
  }
}

interface Vessel { mmsi: number; lat: number; lon: number; sog: number | null; cog: number | null; heading: number | null; name?: string; ship_type?: number }
interface Pair { mmsi_a: number; mmsi_b: number; distance_nm: number; dcpa_nm: number; tcpa_min: number | null; cri: number; domain_intrusion: boolean }

function LiveMap({ vessels }: { vessels: Vessel[] }) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0d100e' } }] },
      center: [21.5, 60.3], zoom: 5.2, attributionControl: false,
    })
    map.on('load', () => { mapRef.current = map; setReady(true) })
    return () => { map.remove(); mapRef.current = null; setReady(false) }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !vessels.length) return
    const pts = {
      type: 'FeatureCollection',
      features: vessels.map((v) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
        properties: { mmsi: String(v.mmsi), sog: v.sog ?? 0, cog: v.cog ?? 0 },
      })),
    } as any
    // heading vector lines (course-over-ground extension)
    const vecs = {
      type: 'FeatureCollection',
      features: vessels.filter((v) => (v.sog ?? 0) > 0.5).map((v) => {
        const k = Math.PI / 180, L = Math.min(0.45, 0.06 + (v.sog ?? 0) * 0.02)
        return {
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: [
            [v.lon, v.lat],
            [v.lon + Math.sin((v.cog ?? 0) * k) * L, v.lat + Math.cos((v.cog ?? 0) * k) * L],
          ] },
          properties: {},
        }
      }),
    } as any
    for (const [id, data] of [['live-v', pts], ['live-vectors', vecs]] as const) {
      if (map.getSource(id)) (map.getSource(id) as any).setData(data)
      else map.addSource(id, { type: 'geojson', data })
    }
    if (!map.getLayer('v-points')) {
      map.addLayer({ id: 'v-vectors', type: 'line', source: 'live-vectors',
        paint: { 'line-color': '#ffb454', 'line-width': 1.2, 'line-opacity': 0.85 } })
      map.addLayer({ id: 'v-points', type: 'circle', source: 'live-v',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 8, 6],
                 'circle-color': '#7adccf', 'circle-stroke-width': 1, 'circle-stroke-color': '#0b0d0c' } })
    }
  }, [vessels, ready])

  return <div ref={el} className="h-[460px] border border-rule" />
}

function HealthStrip() {
  const [h, setH] = useState<any>(null)
  useEffect(() => { j('/v2/health-quality').then(setH) }, [])
  const up = h?.checks?.upstreams ?? {}
  return (
    <div className="panel flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
      <span className="microtype">data quality</span>
      <span className="mono text-xs">rows {h?.checks?.rows?.toLocaleString() ?? '…'}</span>
      <span className="mono text-xs">NaN {h?.checks?.nan_fraction ?? '…'}</span>
      <span className="mono text-xs">IQR pass {h?.checks?.sog_iqr_pass_fraction ?? '…'}</span>
      <span className="mono text-xs">z3 outliers {h?.checks?.speed_outliers_z3 ?? '…'}</span>
      <span className="mono text-xs">ais {up.digitraffic_ais ? <span className="chip chip-ok">UP</span> : <span className="chip chip-bad">DOWN</span>}</span>
      <span className="mono text-xs">met {up.open_meteo ? <span className="chip chip-ok">UP</span> : <span className="chip chip-bad">DOWN</span>}</span>
    </div>
  )
}

function Ticker() {
  const [items, setItems] = useState<string[]>([])
  useEffect(() => {
    j('/v2/live/vessels?limit=40').then((d: any) => {
      if (!d?.vessels) return
      setItems(d.vessels.slice(0, 24).map((v: Vessel) =>
        `MMSI ${v.mmsi}${v.name ? ' · ' + v.name : ''} · ${v.lat.toFixed(2)}N ${v.lon.toFixed(2)}E · SOG ${v.sog ?? '—'}kn`))
    })
  }, [])
  const line = items.join('   ///   ')
  return (
    <div className="ticker hairline-b bg-panel py-1.5">
      <div className="mono text-[11px] text-dim">{line}&nbsp;&nbsp;&nbsp;&nbsp;{line}</div>
    </div>
  )
}

function CollisionWatch() {
  const [pairs, setPairs] = useState<Pair[] | null>(null)
  useEffect(() => {
    const run = () => j('/v2/live/collision').then((d: any) => d && setPairs(d.pairs))
    run()
    const t = setInterval(run, 30000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="panel">
      <div className="flex items-center justify-between px-4 py-2.5 hairline-b">
        <span className="microtype">collision watch · DCPA/TCPA · Goodwin-Stanton domain · fuzzy CRI</span>
        <span className="chip">{pairs?.length ?? 0} encounters ≤15 nm</span>
      </div>
      <table className="dense">
        <thead><tr><th>MMSI A</th><th>MMSI B</th><th>DIST</th><th>DCPA</th><th>TCPA</th><th>CRI</th><th>DOMAIN</th></tr></thead>
        <tbody>
          {(pairs ?? []).map((p, i) => (
            <tr key={i}>
              <td>{p.mmsi_a}</td><td>{p.mmsi_b}</td>
              <td>{p.distance_nm}</td><td>{p.dcpa_nm}</td>
              <td>{p.tcpa_min == null ? '—' : p.tcpa_min + 'm'}</td>
              <td className={p.cri > 0.5 ? 'text-bad' : p.cri > 0.2 ? 'text-warn' : 'text-ok'}>{p.cri.toFixed(3)}</td>
              <td>{p.domain_intrusion ? <span className="chip chip-bad">INSIDE</span> : <span className="chip">clear</span>}</td>
            </tr>
          ))}
          {!pairs?.length && <tr><td colSpan={7} className="text-dim">no encounters within 15 nm of the live fleet right now</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export default function Live() {
  const [vessels, setVessels] = useState<Vessel[]>([])
  const [n, setN] = useState(0)
  useEffect(() => {
    const run = () => j('/v2/live/vessels?limit=300').then((d: any) => {
      if (d?.vessels) { setVessels(d.vessels); setN(d.count) }
    })
    run()
    const t = setInterval(run, 20000)
    return () => clearInterval(t)
  }, [])

  return (
    <main className="mx-auto max-w-7xl px-5 pt-20">
      <Ticker />
      <div className="flex flex-wrap items-end justify-between gap-4 py-5">
        <div>
          <div className="microtype">live fleet · no-signup open feeds</div>
          <h1 className="mt-1 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">Live maritime picture</h1>
        </div>
        <div className="flex gap-6 text-right">
          <div><div className="big-num">{n}</div><div className="microtype">vessels tracked</div></div>
          <div><div className="big-num">20<span className="unit">s refresh</span></div><div className="microtype">poll interval</div></div>
        </div>
      </div>
      <HealthStrip />
      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="panel">
          <div className="microtype px-4 py-2.5 hairline-b">positions · heading vectors · Digitraffic Finland AIS (CC BY 4.0)</div>
          <LiveMap vessels={vessels} />
        </div>
        <div className="panel max-h-[500px] overflow-y-auto">
          <div className="microtype px-4 py-2.5 hairline-b">fleet register · top {Math.min(vessels.length, 200)}</div>
          <table className="dense">
            <thead><tr><th>MMSI</th><th>NAME</th><th>SOG</th><th>COG</th></tr></thead>
            <tbody>
              {vessels.slice(0, 200).map((v) => (
                <tr key={v.mmsi}>
                  <td>{v.mmsi}</td>
                  <td className="truncate max-w-[140px]">{v.name ?? '—'}</td>
                  <td>{v.sog ?? '—'}</td>
                  <td>{v.cog ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <CollisionWatch />
        <WeatherPanel />
      </div>
      <Footer />
    </main>
  )
}

function WeatherPanel() {
  const [w, setW] = useState<any>(null)
  useEffect(() => { j('/v2/live/weather?lat=60.15&lon=24.95').then(setW) }, [])
  const om = w?.open_meteo_current
  const omM = w?.open_meteo_marine
  const nws = w?.nws
  const buoys = (w?.ndbc_buoys ?? []).slice(0, 6)
  return (
    <div className="panel">
      <div className="microtype px-4 py-2.5 hairline-b">weather stack · Open-Meteo · NOAA NWS · NOAA NDBC</div>
      <div className="grid grid-cols-2 gap-px">
        <div className="p-4 hairline-r">
          <div className="microtype">open-meteo current</div>
          <div className="big-num mt-1">{om?.wind_speed_10m ?? '—'}<span className="unit"> kn</span></div>
          <div className="mono mt-1 text-xs text-dim">gusts {om?.wind_gusts_10m ?? '—'} · precip {om?.precipitation ?? '—'} · {om?.temperature_2m ?? '—'}°C</div>
          <div className="mono mt-2 text-xs text-dim">waves {omM?.wave_height ?? '—'} m · {omM?.wave_period ?? '—'} s · swell {omM?.swell_wave_height ?? '—'} m</div>
        </div>
        <div className="p-4">
          <div className="microtype">nws point forecast</div>
          {nws?.available ? (
            <div className="mono mt-1 space-y-1 text-xs">
              {(nws.periods ?? []).slice(0, 3).map((p: any, i: number) => (
                <div key={i}>{p.name}: {p.temp_c?.toFixed(0)}°C · {p.wind_kn} {p.dir} · {p.short}</div>
              ))}
            </div>
          ) : <div className="mono mt-1 text-xs text-dim">US grid only — outside coverage at this point</div>}
        </div>
      </div>
      <div className="hairline-t">
        <table className="dense">
          <thead><tr><th>NDBC</th><th>WVHT m</th><th>DPD s</th><th>WSPD m/s</th><th>SST °C</th></tr></thead>
          <tbody>
            {buoys.map((b: any) => (
              <tr key={b.station}><td>{b.station}</td><td>{b.wave_height_m}</td><td>{b.dominant_period_s}</td><td>{b.wind_speed_ms}</td><td>{b.sea_temp_c}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
