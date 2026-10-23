import { Link } from 'react-router-dom'
import { Footer } from '../components/chrome'
import type { EvalJson, StatsJson } from '../lib/data'
import { useArtifact } from '../lib/data'

function MetricStrip() {
  const evalData = useArtifact<EvalJson>('eval.json', 'metrics')
  const stats = useArtifact<StatsJson>('stats.json')
  const cells = evalData && stats
    ? [
        { v: evalData.global.p50.mae_h.toFixed(2) + ' h', l: 'test MAE (P50 · GPU)' },
        { v: (evalData.coverage_p10_p90 * 100).toFixed(1) + '%', l: 'P10–P90 coverage' },
        { v: (100 * (1 - evalData.global.p50.mae_h / evalData.global.baseline_speed_prior.mae_h)).toFixed(0) + '%', l: 'vs speed prior' },
        { v: stats.total_voyages.toLocaleString(), l: 'voyages modeled' },
        { v: stats.total_samples.toLocaleString(), l: 'AIS + ERA5 rows' },
      ]
    : null
  return (
    <div className="grid grid-cols-2 border border-rule sm:grid-cols-5">
      {cells
        ? cells.map((c) => (
            <div key={c.l} className="hairline-r px-4 py-3">
              <div className="big-num">{c.v}</div>
              <div className="microtype mt-1">{c.l}</div>
            </div>
          ))
        : (
          <div className="col-span-2 px-4 py-3 text-dim sm:col-span-5">
            <span className="mono text-xs">metrics appear after the training pipeline runs — make data && make train. no synthetic numbers, ever.</span>
          </div>
        )}
    </div>
  )
}

const FEATURES = [
  ['LIVE AIS', 'Real-time fleet picture from Digitraffic Finland (CC BY 4.0, keyless) — positions, heading vectors, 20 s refresh.'],
  ['COLLISION WATCH', 'DCPA/TCPA encounter solver, Goodwin-Stanton ship-domain ellipses, fuzzy Collision Risk Index — ranked continuously.'],
  ['KALMAN TRACKING', 'EKF and UKF trackers over raw fixes, Douglas-Peucker simplification, cubic-spline reconstruction, Frechet residuals.'],
  ['ANOMALY ENSEMBLE', 'Isolation Forest + Gaussian Mixture + Mahalanobis distance, trained on historical AIS, served per-point.'],
  ['SPATIAL INTELLIGENCE', 'H3 hexagon density, HDBSCAN anchorage clusters, Little\u2019s Law + M/M/c berth queues, networkx A*/Dijkstra routing.'],
  ['FUEL & EMISSIONS', 'ITTC-1978 friction, Townsin-Glover added wave resistance, IMO CO2 factors — per-voyage fuel and carbon intensity.'],
  ['WEATHER STACK', 'Open-Meteo forecast + marine waves, NOAA NWS point forecasts, NDBC realtime buoys — no signup anywhere.'],
  ['OCEAN CONTEXT', 'ETOPO1 bathymetry profiles via ERDDAP, Marine Regions MPAs, USGS seismicity, OBIS/GBIF occurrence records.'],
]

export default function Landing() {
  return (
    <main>
      <section className="hairline-b relative">
        <div className="basetexture absolute inset-0" aria-hidden />
        <div className="relative mx-auto max-w-7xl px-5 py-20">
          <div className="microtype">idealab #586938 → shipped open source · voyance II</div>
          <h1 className="mt-4 max-w-4xl font-[family-name:var(--font-display)] text-4xl font-bold leading-[1.05] tracking-tight sm:text-6xl">
            Know where your ETA model fails,
            <span className="text-acc"> before the storm does.</span>
          </h1>
          <p className="mt-5 max-w-2xl leading-relaxed text-dim">
            A live maritime intelligence terminal: real-time AIS tracking and collision
            watch, GPU-trained quantile ETA with conformal uncertainty, and dense
            analytics — H3 density, anchorage queues, route optimization, fuel and
            carbon. Built entirely on open data. No signups. No synthetic numbers.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link to="/live" className="btn btn-acc">OPEN LIVE TERMINAL</Link>
            <Link to="/analytics" className="btn">ANALYTICS WORKBENCH</Link>
            <Link to="/docs" className="btn">CURL ONE PREDICTION</Link>
          </div>
          <div className="mt-12">
            <MetricStrip />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-14">
        <div className="microtype">capabilities</div>
        <div className="mt-4 grid gap-px border border-rule md:grid-cols-4">
          {FEATURES.map(([t, d]) => (
            <div key={t} className="panel-flat p-5">
              <div className="mono text-xs font-semibold text-acc">{t}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-dim">{d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 pb-14">
        <div className="microtype">data sources · every one free, every one keyless</div>
        <div className="mt-4 flex flex-wrap gap-2">
          {['NOAA MarineCadastre AIS', 'NOAA NWS api.weather.gov', 'NOAA NDBC buoys', 'NOAA ERDDAP ETOPO1',
            'Open-Meteo forecast+marine', 'Digitraffic Finland AIS', 'Danish Maritime Authority AIS',
            'Marine Regions WFS', 'UN/LOCODE', 'USGS Earthquakes', 'OBIS', 'GBIF', 'OpenStreetMap Overpass',
            'Natural Earth', 'NOAA CoastGuard archives'].map((s) => (
            <span key={s} className="chip">{s}</span>
          ))}
        </div>
        <p className="mt-4 max-w-3xl text-[13px] leading-relaxed text-dim">
          Historical model training uses the NOAA MarineCadastre archive; the live
          terminal uses only live feeds. Training happens on GPU (XGBoost CUDA
          quantiles + GPU random forest); serving is CPU-inference.
        </p>
      </section>

      <Footer />
    </main>
  )
}
