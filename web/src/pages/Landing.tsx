import { Link } from 'react-router-dom'
import OceanCanvas from '../components/OceanCanvas'
import { Footer, Reveal } from '../components/chrome'
import type { EvalJson, StatsJson } from '../lib/data'
import { useArtifact } from '../lib/data'

function Kinetic({ text, className = '' }: { text: string; className?: string }) {
  return (
    <span className={`kinetic ${className}`}>
      {text.split(' ').map((w, i) => (
        <span className="word" key={i}>
          <span style={{ animationDelay: `${i * 70}ms` }}>&nbsp;{w}</span>
        </span>
      ))}
    </span>
  )
}

function MetricStrip() {
  const evalData = useArtifact<EvalJson>('eval.json', 'metrics')
  const stats = useArtifact<StatsJson>('stats.json')
  const loaded = evalData && stats
  const cells = loaded
    ? [
        { v: evalData!.global.p50.mae_h.toFixed(2) + ' h', l: 'test MAE (P50)' },
        { v: (evalData!.coverage_p10_p90 * 100).toFixed(1) + '%', l: 'P10–P90 coverage' },
        {
          v:
            (100 * (1 - evalData!.global.p50.mae_h / evalData!.global.baseline_speed_prior.mae_h)).toFixed(0) + '%',
          l: 'better than speed prior',
        },
        { v: stats!.total_voyages.toLocaleString(), l: 'real voyages modeled' },
        { v: stats!.total_samples.toLocaleString(), l: 'AIS + weather samples' },
      ]
    : null
  return (
    <div className="glass mx-auto mt-10 grid max-w-4xl grid-cols-2 gap-px overflow-hidden rounded-2xl sm:grid-cols-5">
      {cells
        ? cells.map((c) => (
            <div key={c.l} className="px-4 py-4 text-center">
              <div className="font-[family-name:var(--font-mono)] text-xl font-semibold text-bio">{c.v}</div>
              <div className="mt-1 text-[11px] uppercase tracking-wider text-mist/80">{c.l}</div>
            </div>
          ))
        : (
          <div className="col-span-2 px-4 py-4 text-center text-mist sm:col-span-5">
            Real metrics appear here once the training pipeline has run — <code className="text-bio">make data && make train</code>. No synthetic numbers are ever shown.
          </div>
        )}
    </div>
  )
}

const FEATURES = [
  {
    t: 'Quantile ETA, not point guesses',
    d: 'LightGBM P10/P50/P90 models give calibrated uncertainty per prediction. Ships, routes, and weather decide the band width — not vibes.',
    span: 'md:col-span-2',
    icon: 'M3 12h4l3-8 4 16 3-8h4',
  },
  {
    t: 'Error decomposed the way ops thinks',
    d: 'MAE sliced by Beaufort wind class, sea region, vessel type, and distance bucket. Find where the model fails before your schedule does.',
    span: '',
    icon: 'M4 20V10m6 10V4m6 16v-7',
  },
  {
    t: 'Drift monitoring with alerts',
    d: 'Evidently reports on weekly slices: PSI/KS per feature plus MAE ratio vs baseline. Alerts flow to the API and the dashboard.',
    span: '',
    icon: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  },
  {
    t: 'Open end to end',
    d: 'NOAA MarineCadastre AIS (CC0) + Open-Meteo ERA5 (CC BY 4.0) + UN/LOCODE. Apache-2.0 code. Every metric on this site is reproducible.',
    span: 'md:col-span-2',
    icon: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 0c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9m0-18c-2.5 2.5-3.5 5.5-3.5 9s1 6.5 3.5 9M3.5 9h17m-17 6h17',
  },
  {
    t: 'Research-grade reporting',
    d: 'Model card, benchmark vs baselines, calibration, drift dossiers — written like a paper, exported as PDF, wired to the live API.',
    span: '',
    icon: 'M8 3h8l4 4v14H4V3h4Zm0 8h8M8 15h8',
  },
  {
    t: 'Self-host or embed',
    d: 'One FastAPI container behind a REST contract (/v1/predict) with OpenAPI schema, Prometheus metrics, and a static dashboard you can iframe.',
    span: 'md:col-span-2',
    icon: 'M4 7h16M4 12h16M4 17h10',
  },
]

const COMPETITORS = [
  ['Windward — Maritime AI / Predicted ETA', 'Closed, enterprise pricing', 'Operational visibility product; ETA accuracy is a marketing claim, not an open benchmark'],
  ['PortXchange — ETAPredictor', 'Closed', 'Port-arrival planning; no open error decomposition or drift reporting'],
  ['WHIZTEC — Predictive ETA', 'Closed', 'Freight-focused; no public model card'],
  ['Broadpath Logistics', 'Closed', 'Multimodal tracking platform'],
  ['Kairon', 'Closed', 'Speed optimization via public AIS'],
  ['WUT-TrajData', 'Open dataset', 'Trajectory-prediction benchmark, not a served model'],
  ['Voyance (this project)', 'Apache-2.0', 'Served quantile ETA + honest error decomposition + drift monitoring on public data'],
]

export default function Landing() {
  return (
    <main>
      {/* HERO */}
      <section className="relative flex min-h-[92vh] flex-col justify-center overflow-hidden">
        <div className="aurora" />
        <OceanCanvas />
        <div className="grid-lines absolute inset-0 opacity-60" />
        <div className="relative mx-auto max-w-6xl px-6 pt-32">
          <div className="tag">Idea #586938 → shipped open source</div>
          <h1 className="mt-4 max-w-4xl font-[family-name:var(--font-display)] text-5xl leading-[1.04] sm:text-7xl">
            <Kinetic text="Know where your" />
            <br />
            <Kinetic text="ETA model fails —" className="shimmer" />
            <br />
            <Kinetic text="before the storm does." />
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-mist">
            Voyance is an open-source maritime voyage-intelligence platform: AIS-grounded ETA models
            with weather-conditioned uncertainty bands, error decomposed by wind, region and vessel
            type, and drift monitoring — trained on NOAA MarineCadastre AIS joined to ERA5 reanalysis.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/dashboard"
              className="rounded-xl bg-bio px-6 py-3 font-semibold text-abyss transition hover:bg-bio-dim"
            >
              Open the dashboards
            </Link>
            <Link
              to="/docs"
              className="rounded-xl border border-mist/25 px-6 py-3 font-semibold transition hover:border-bio/50 hover:text-bio"
            >
              curl one prediction
            </Link>
          </div>
          <MetricStrip />
        </div>
      </section>

      {/* PROBLEM */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <Reveal>
          <div className="tag">The gap</div>
          <h2 className="mt-3 max-w-3xl font-[family-name:var(--font-display)] text-3xl sm:text-4xl">
            Operators judge models from vendor claims. Weather decides reality.
          </h2>
          <p className="mt-4 max-w-3xl leading-relaxed text-mist">
            A fleet team trusts an arrival estimate but cannot see where it fails in bad weather or
            certain waters. Public ship-location data now makes an outside measure of performance
            practical every week — so we built the model and the scorecard in one open product.
          </p>
        </Reveal>
      </section>

      {/* BENTO FEATURES */}
      <section className="mx-auto max-w-6xl px-6">
        <Reveal><div className="tag">What you get</div></Reveal>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal key={f.t} delay={i * 0.05} className={f.span}>
              <div className="bento h-full p-6">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#29e6d2" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={f.icon} />
                </svg>
                <h3 className="mt-4 font-[family-name:var(--font-display)] text-lg font-semibold">{f.t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mist">{f.d}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* PIPELINE */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <Reveal>
          <div className="tag">How it works</div>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl sm:text-4xl">
            From raw AIS radio pings to served quantiles
          </h2>
        </Reveal>
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          {[
            ['01', 'Ingest', 'Daily US AIS broadcast points (NOAA MarineCadastre, CC0), port gazetteer from UN/LOCODE.'],
            ['02', 'Voyageize', 'Port-buffer segmentation finds departures and arrivals; samples keep real timestamps, SOG, distance-to-go.'],
            ['03', 'Weatherize', 'Each sample joins hourly ERA5 wind, gusts, precipitation, humidity and ERA5 waves/swell on a 0.5° grid.'],
            ['04', 'Serve + watch', 'LightGBM quantile models train temporally; Evidently watches weekly slices and fires drift alerts.'],
          ].map(([n, t, d], i) => (
            <Reveal key={n} delay={i * 0.06}>
              <div className="bento h-full p-6">
                <div className="font-[family-name:var(--font-mono)] text-bio">{n}</div>
                <h3 className="mt-2 font-semibold">{t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mist">{d}</p>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal delay={0.1}>
          <img
            src="/architecture.png"
            alt="Voyance architecture: open data sources → pipeline → artifacts → serving"
            className="glass mt-8 w-full rounded-2xl p-4"
          />
        </Reveal>
      </section>

      {/* COMPETITIVE MATRIX */}
      <section className="mx-auto max-w-6xl px-6">
        <Reveal>
          <div className="tag">Landscape (from idealab #586938 market analysis)</div>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl sm:text-4xl">
            Closest players — and the open slot
          </h2>
        </Reveal>
        <Reveal delay={0.08}>
          <div className="glass mt-8 overflow-x-auto rounded-2xl">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-mist/80">
                <tr className="border-b border-mist/10">
                  <th className="px-5 py-4 font-medium">Player</th>
                  <th className="px-5 py-4 font-medium">Model / access</th>
                  <th className="px-5 py-4 font-medium">What that means for you</th>
                </tr>
              </thead>
              <tbody>
                {COMPETITORS.map(([n, a, d], i) => (
                  <tr key={n} className={`border-b border-mist/5 ${i === COMPETITORS.length - 1 ? 'bg-bio/5' : ''}`}>
                    <td className="px-5 py-4 font-medium">{i === COMPETITORS.length - 1 ? <span className="text-bio">{n}</span> : n}</td>
                    <td className="px-5 py-4 text-mist">{a}</td>
                    <td className="px-5 py-4 text-mist">{d}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
      </section>

      {/* OPEN SOURCE PRICING */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <Reveal>
          <div className="tag">Pricing</div>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl sm:text-4xl">
            It's open source. The price is your compute.
          </h2>
        </Reveal>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[
            ['Self-host', '$0', 'Train on your own machine with public data; serve with Docker Compose.', true],
            ['Hosted data packs', 'cost of storage', 'Pre-built feature stores and model weights published as release artifacts.', false],
            ['Fleet integration', 'open RFC', 'Bring your own inference logs; the scorecard contract is documented and versioned.', false],
          ].map(([t, p, d, hot], i) => (
            <Reveal key={t as string} delay={i * 0.05}>
              <div className={`bento h-full p-6 ${hot ? 'border-bio/40' : ''}`}>
                <div className="flex items-baseline justify-between">
                  <h3 className="font-[family-name:var(--font-display)] text-xl font-semibold">{t as string}</h3>
                  <span className="font-[family-name:var(--font-mono)] text-bio">{p as string}</span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-mist">{d as string}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* RESEARCH TEASER */}
      <section className="mx-auto max-w-6xl px-6 pb-8">
        <Reveal>
          <div className="bento relative overflow-hidden p-10 text-center">
            <div className="aurora" />
            <div className="relative">
              <div className="tag">Research</div>
              <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl">
                Papers, methodology, and every chart behind the numbers
              </h2>
              <p className="mx-auto mt-3 max-w-2xl text-mist">
                The hybrid-ML ETA literature (Saber 2025, Noman 2025), drift-detection benchmarks
                (arXiv:2404.18673), and our own evaluation — all linked, all reproducible.
              </p>
              <Link to="/research" className="mt-6 inline-block rounded-xl bg-bio px-6 py-3 font-semibold text-abyss transition hover:bg-bio-dim">
                Read the research
              </Link>
            </div>
          </div>
        </Reveal>
      </section>

      <Footer />
    </main>
  )
}
