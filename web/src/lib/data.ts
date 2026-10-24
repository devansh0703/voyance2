import { useEffect, useState } from 'react'

/**
 * Data layer: loads real pipeline artifacts from /data/*.json.
 * When the FastAPI backend is live, /v1/* endpoints take precedence.
 * No mock data anywhere: a missing artifact surfaces an honest
 * "pipeline not run" state to the UI.
 */

async function tryApi(path: string): Promise<unknown | null> {
  try {
    const r = await fetch(`/v1/${path}`, { signal: AbortSignal.timeout(2500) })
    if (!r.ok) return null
    return await r.json()
  } catch {
    return null
  }
}

async function tryStatic(name: string): Promise<unknown | null> {
  try {
    const r = await fetch(`/data/${name}`)
    if (!r.ok) return null
    return await r.json()
  } catch {
    return null
  }
}

export function useArtifact<T>(name: string, apiPath?: string): T | null {
  const [data, setData] = useState<T | null>(null)
  useEffect(() => {
    let alive = true
    ;(async () => {
      let d = apiPath ? await tryApi(apiPath) : null
      if (d == null) d = await tryStatic(name)
      if (alive) setData(d as T)
    })()
    return () => { alive = false }
  }, [name, apiPath])
  return data
}

export interface EvalJson {
  model: string
  trained_on: string[]
  test_on: string[]
  train_rows: number
  test_rows: number
  global: {
    p50: { mae_h: number; rmse_h: number; mape: number }
    baseline_speed_prior: { mae_h: number; rmse_h: number; mape: number }
  }
  coverage_p10_p90: number
  mean_interval_width_h: number
  conformal_adjustment_h?: number
  feature_importance: { feature: string; gain: number }[]
  breakdown_p50: Record<string, Record<string, { mae_h: number; n: number; p90_err_h: number }>>
  daily_mae: Record<string, number>
}

export interface DriftWeek {
  slice?: string
  week?: string
  n: number
  mae_h: number
  mae_ratio_vs_test_overall?: number | null
  drifted_features: { feature: string; psi: number }[]
  psi_own?: Record<string, number>
  alert: boolean
}

export interface DriftJson {
  baseline: string
  monitor: string | string[]
  reference_mae_h?: number
  weeks: DriftWeek[]
  n_drifted_features_total?: number
}

export interface StatsJson {
  months: { month: string; voyages: number; samples: number; vessels: number }[]
  by_region: Record<string, number>
  by_type: Record<string, number>
  by_beaufort: Record<string, number>
  weather_ok_fraction: number
  total_voyages: number
  total_samples: number
}

export interface MapJson {
  voyages: {
    voyage_id: string
    vessel_type_group: string
    dep_port: string
    arr_port: string
    dep_port_idx?: number
    arr_port_idx?: number
    duration_h: number
    coords: [number, number][] // [lon, lat]
    err_pct: number | null // |error|/remaining time where model predictions exist
  }[]
  lanes: [number, number, number][] // [lat, lng, weight]
}
