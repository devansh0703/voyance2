import { useState } from 'react'
import { Footer, Reveal } from '../components/chrome'

const QUICKSTART = `# clone + environment
git clone https://github.com/devansh-voyance/voyance && cd voyance
uv venv .venv && uv pip install -r requirements.txt   # or: pip install -r requirements.txt

# 1. fetch data (AIS weeks + weather; ~30 GB disk, resumable)
make data

# 2. train + evaluate + drift reports
make train && make drift

# 3. serve API + dashboard
make api          # FastAPI on :8000
make web          # static dashboard on :5173 (dev) or dist/ via the API`

const PREDICT = `curl -s -X POST localhost:8000/v1/predict \\
  -H 'content-type: application/json' \\
  -d '{
        "lat": 33.7, "lon": -118.2,
        "vessel_type_group": "tanker",
        "vessel_length": 250,
        "vessel_draft": 12.5,
        "sog": 12.4, "sog_median_6h": 12.9,
        "distance_traveled_nm": 820, "elapsed_h": 68,
        "month": 7, "hour": 14,
        "dest_lat": 37.79, "dest_lon": -122.27
      }'

# → {
#     "p50_h": 22.41, "p10_h": 19.02, "p90_h": 26.87,
#     "remaining_distance_nm": 631.2,
#     "beaufort_class": 3,
#     "model_version": "lightgbm-quantile-eta v1.0.0"
#   }`

const ENDPOINTS: [string, string, string][] = [
  ['POST', '/v1/predict', 'Quantile ETA for a vessel state vector; returns P10/P50/P90 hours + context'],
  ['GET', '/v1/metrics', 'Evaluation JSON: global + per-condition MAE, coverage, feature importance'],
  ['GET', '/v1/drift', 'Weekly drift summary + active alerts'],
  ['GET', '/v1/voyages', 'Processed voyage samples (filter by region/type)'],
  ['GET', '/v1/weather', 'Live Open-Meteo forecast proxy (attribution: CC BY 4.0)'],
  ['GET', '/health', 'Liveness + model artifact check'],
  ['GET', '/metrics', 'Prometheus instrumentation'],
]

export default function Docs() {
  const [copied, setCopied] = useState('')
  const copy = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(''), 1500)
  }
  return (
    <main className="mx-auto max-w-6xl px-6 pt-28">
      <Reveal>
        <div className="tag">Docs</div>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl">Quickstart & API</h1>
      </Reveal>

      <section className="mt-10 grid gap-6 lg:grid-cols-2">
        <Reveal>
          <div className="bento overflow-hidden">
            <div className="flex items-center justify-between border-b border-mist/10 px-5 py-3">
              <span className="tag">Terminal</span>
              <button onClick={() => copy('qs', QUICKSTART)} className="text-xs text-mist hover:text-bio">
                {copied === 'qs' ? 'copied ✓' : 'copy'}
              </button>
            </div>
            <pre className="overflow-x-auto p-5 font-[family-name:var(--font-mono)] text-xs leading-relaxed text-mist">{QUICKSTART}</pre>
          </div>
        </Reveal>
        <Reveal delay={0.05}>
          <div className="bento overflow-hidden">
            <div className="flex items-center justify-between border-b border-mist/10 px-5 py-3">
              <span className="tag">One prediction</span>
              <button onClick={() => copy('pr', PREDICT)} className="text-xs text-mist hover:text-bio">
                {copied === 'pr' ? 'copied ✓' : 'copy'}
              </button>
            </div>
            <pre className="overflow-x-auto p-5 font-[family-name:var(--font-mono)] text-xs leading-relaxed text-mist">{PREDICT}</pre>
          </div>
        </Reveal>
      </section>

      <section className="mt-12">
        <Reveal><h2 className="font-[family-name:var(--font-display)] text-2xl">REST surface</h2></Reveal>
        <div className="glass mt-4 overflow-x-auto rounded-2xl">
          <table className="w-full min-w-[640px] text-left text-sm">
            <tbody>
              {ENDPOINTS.map(([m, p, d]) => (
                <tr key={p + m} className="border-b border-mist/5 last:border-0">
                  <td className="px-5 py-3"><span className={`rounded px-2 py-0.5 font-mono text-xs ${m === 'POST' ? 'bg-gold/15 text-gold' : 'bg-bio/10 text-bio'}`}>{m}</span></td>
                  <td className="px-5 py-3 font-mono text-xs">{p}</td>
                  <td className="px-5 py-3 text-mist">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-mist">
          Full OpenAPI schema at <code className="text-bio">/docs</code> when the API runs.
        </p>
      </section>

      <Footer />
    </main>
  )
}
