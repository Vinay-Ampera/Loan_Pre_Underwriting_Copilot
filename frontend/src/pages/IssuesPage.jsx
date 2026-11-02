import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Callout from '../components/Callout'
import StatusChip from '../components/StatusChip'
import { Skeleton } from '../components/States'
import './IssuesPage.css'

export const CATEGORIES = [
  ['bug', 'Something is broken'],
  ['wrong_result', 'A result looks wrong'],
  ['access', 'I cannot get to something'],
  ['other', 'Something else'],
]
export const ISSUE_STATUS = {
  open: ['info', 'Open'],
  read: ['refer', 'Read by admin'],
  closed: ['done', 'Closed'],
}

export function IssueChip({ status }) {
  const [tone, label] = ISSUE_STATUS[status] || ['neutral', status]
  return <StatusChip tone={tone}>{label}</StatusChip>
}

/** An officer reports a problem with the tool to the admin. No personal data may be pasted. */
export default function IssuesPage() {
  const { data, loading, reload } = useAsync(() => api.get('/issues'), [])
  const [form, setForm] = useState({ category: 'bug', case_ref: '', body: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const ready = form.body.trim().length >= 10

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setDone(false)
    try {
      await api.post('/issues', {
        category: form.category,
        case_ref: form.case_ref.trim().toUpperCase() || null,
        body: form.body.trim(),
      })
      setForm({ category: form.category, case_ref: '', body: '' })
      setDone(true)
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="issues">
      <header>
        <h1>Report a problem</h1>
        <p className="muted">Tell the admin about something wrong with the tool.</p>
      </header>
      <Callout tone="warn" title="Do not paste personal data">
        No names, PAN, Aadhaar, phone numbers, account numbers or email addresses. A report that
        contains any of them is refused. A case reference such as CASE-2026-0001 is fine.
      </Callout>
      <form className="card issue-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="i-cat">What kind of problem?</label>
          <select id="i-cat" className="select" value={form.category} onChange={set('category')}>
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="i-ref">
            Case reference <span className="opt">(optional)</span>
          </label>
          <input
            id="i-ref"
            className="input mono"
            placeholder="CASE-2026-0001"
            value={form.case_ref}
            onChange={set('case_ref')}
          />
        </div>
        <div className="field">
          <label htmlFor="i-body">What happened?</label>
          <textarea
            id="i-body"
            className="textarea"
            rows={5}
            maxLength={1000}
            value={form.body}
            onChange={set('body')}
          />
          <span className="small muted">
            {form.body.trim().length}/1000 · at least 10 characters
          </span>
        </div>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        {done && (
          <p className="ok-note" role="status">
            Thank you. Your report was sent to the admin.
          </p>
        )}
        <div>
          <button type="submit" className="btn btn-primary" disabled={!ready || busy}>
            Send report
          </button>
        </div>
      </form>

      <section aria-label="Your reports">
        <h2>Your reports</h2>
        {loading && <Skeleton lines={2} height={40} />}
        {data && data.length === 0 && <p className="muted">You have not reported anything.</p>}
        {data && data.length > 0 && (
          <ul className="issue-list card">
            {data.map((i) => (
              <li key={i.id}>
                <div>
                  <p>{i.body}</p>
                  <p className="small muted">
                    {CATEGORIES.find((c) => c[0] === i.category)?.[1]}
                    {i.case_ref && ` · ${i.case_ref}`} · {new Date(i.created_at).toLocaleString()}
                  </p>
                </div>
                <IssueChip status={i.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
