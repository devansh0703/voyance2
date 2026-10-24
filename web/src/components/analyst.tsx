import { useEffect, useState } from 'react'

const API = ''

/** minimal markdown renderer: ##/### headings, bullets, bold */
function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="space-y-2">
      {lines.map((ln, i) => {
        const bold = (t: string) => t.split(/\*\*(.+?)\*\*/g).map((seg, k) =>
          k % 2 ? <strong key={k} className="text-paper">{seg}</strong> : seg)
        if (ln.startsWith('## ')) return <h3 key={i} className="font-[family-name:var(--font-display)] text-base font-bold text-acc pt-1">{ln.slice(3)}</h3>
        if (ln.startsWith('### ')) return <h4 key={i} className="font-semibold text-acc text-sm pt-1">{ln.slice(4)}</h4>
        if (ln.startsWith('- ') || ln.startsWith('* '))
          return <div key={i} className="flex gap-2 text-[13px] leading-relaxed"><span className="text-acc">▸</span><span>{bold(ln.slice(2))}</span></div>
        if (!ln.trim()) return <div key={i} className="h-1" />
        return <p key={i} className="text-[13px] leading-relaxed">{bold(ln)}</p>
      })}
    </div>
  )
}

export default function AIExplain({ voyageId }: { voyageId: string }) {
  const [providers, setProviders] = useState<any[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [question, setQuestion] = useState('Why will this route drift tomorrow for this ship type?')
  const [answer, setAnswer] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    fetch(API + '/v2/ai/providers').then((r) => r.json()).then((d) => {
      setProviders(d.chain ?? [])
      const live = (d.chain ?? []).find((p: any) => p.chat_ok) ||
                   (d.chain ?? []).find((p: any) => p.reachable)
      if (live) { setProvider(live.provider); setModel(live.models?.[0] ?? '') }
    })
  }, [])
  const run = (q?: string) => {
    setBusy(true); setAnswer(null)
    fetch(API + '/v2/ai/explain', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ voyage_id: voyageId, question: q ?? question, provider: provider || null, model: model || null }) })
      .then((r) => r.json()).then(setAnswer)
      .finally(() => setBusy(false))
  }
  return (
    <div className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2" style={{ borderBottom: '1px solid var(--color-rule)', paddingBottom: 10 }}>
        <span className="microtype">AI maritime analyst · parsed answer with reference backing</span>
        <div className="flex gap-2">
          <select className="btn" value={provider} onChange={(e) => {
            setProvider(e.target.value)
            const p = providers.find((x: any) => x.provider === e.target.value)
            setModel(p?.models?.[0] ?? '')
          }}>
            {providers.map((p: any) => (
              <option key={p.provider} value={p.provider}>{p.provider}{p.chat_ok ? '' : p.reachable ? ' (chat blocked)' : ' (unreachable)'}</option>
            ))}
          </select>
          <select className="btn" value={model} onChange={(e) => setModel(e.target.value)}>
            {(providers.find((x: any) => x.provider === provider)?.models ?? []).map((m: string) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {['Why will this route drift tomorrow for this ship type?',
          'What weather risks should the fleet team watch on the remaining leg?',
          'How reliable is this ETA, and what does the historical record show?'].map((q) => (
          <button key={q} className={`btn ${question === q ? 'btn-acc' : ''}`} onClick={() => { setQuestion(q); run(q) }}>
            {q.slice(0, 34)}…
          </button>
        ))}
        <button className="btn btn-acc" onClick={() => run()} disabled={busy}>
          {busy ? 'ANALYZING…' : 'ASK'}
        </button>
      </div>
      {busy && <div className="mono mt-3 text-xs text-dim">building context packet: live forecast + historical analogs + model performance → provider…</div>}
      {answer && (
        <div className="mt-4" style={{ borderTop: '1px solid var(--color-rule)', paddingTop: 12 }}>
          <div className="microtype mb-2">
            served by {answer.provider} · {answer.model} · references below are real historical voyages
          </div>
          <Markdown text={answer.answer ?? ''} />
          {(answer.references ?? []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {answer.references.map((r: any) => (
                <a key={r.voyage_id} href={r.replay_url} className="chip chip-ok">
                  {r.voyage_id.slice(0, 18)} · {r.label}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

