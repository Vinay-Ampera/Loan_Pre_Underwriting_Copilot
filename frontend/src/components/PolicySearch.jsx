import { useState } from 'react'
import { api } from '../api/client'
import { LOAN_ONLY, pct, policyLabel } from '../lib/policy'
import './PolicySearch.css'

function Hits({ title, hits }) {
  return (
    <section className="ps-col" aria-label={title}>
      <h4>{title}</h4>
      {hits.length === 0 && <p className="muted small">No clause was close enough.</p>}
      <ol className="ps-hits">
        {hits.map((h) => (
          <li key={h.clause_id}>
            <p>
              <span className="mono ref-id">{h.clause_id}</span> <strong>{h.title}</strong>{' '}
              <span className="small muted">match {pct(h.relevance)}</span>
            </p>
            <p className="small">{h.text}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

/**
 * Ask a question and see the clauses the Policy agent would be given: the common policy plus the
 * chosen loan type. The admin can put the drafts beside the version in force.
 */
export default function PolicySearch({ admin = false }) {
  const [q, setQ] = useState('')
  const [lt, setLt] = useState('home')
  const [draft, setDraft] = useState(false)
  const [out, setOut] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run(e) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      const params = new URLSearchParams({ q, loan_type: lt, draft: String(admin && draft) })
      setOut(await api.get(`/knowledge/search?${params}`))
    } catch (err) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="policy-search">
      <form className="ps-form" onSubmit={run} aria-label="Search the policy">
        <label className="field ps-q">
          <span className="field-label">Question</span>
          <input
            className="input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="for example: minimum credit score for a home loan"
            maxLength={300}
          />
        </label>
        <label className="field">
          <span className="field-label">Loan type</span>
          <select className="select" value={lt} onChange={(e) => setLt(e.target.value)}>
            {LOAN_ONLY.map((t) => (
              <option key={t} value={t}>
                {policyLabel(t)}
              </option>
            ))}
          </select>
        </label>
        {admin && (
          <label className="ps-draft">
            <input type="checkbox" checked={draft} onChange={(e) => setDraft(e.target.checked)} />
            Compare with drafts
          </label>
        )}
        <button type="submit" className="btn btn-primary" disabled={busy || q.trim().length < 3}>
          Search
        </button>
      </form>
      {msg && (
        <p className="field-error" role="alert">
          {msg}
        </p>
      )}
      {out && (
        <div className="ps-results">
          <Hits title="Policy in force" hits={out.active} />
          {out.draft && <Hits title="With the drafts" hits={out.draft} />}
          {admin && draft && !out.draft && (
            <p className="small muted">There is no checked draft for this loan type or common.</p>
          )}
        </div>
      )}
    </div>
  )
}
