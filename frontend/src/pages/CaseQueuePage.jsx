import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import CaseQueueTable from '../components/CaseQueueTable'
import ExportButton from '../components/ExportButton'
import { queryOf } from '../lib/download'
import { EmptyState, ErrorState } from '../components/States'
import { LOAN_TYPES } from '../components/LoanTypePicker'
import { VIEWS, matchesView } from '../lib/views'
import './CaseQueuePage.css'
import { SectionLoader } from '../components/Loading'

const STATUSES = [
  ['', 'All statuses'],
  ['draft', 'Draft'],
  ['uploaded', 'Documents uploaded'],
  ['applicant_submitted', 'Applicant submitted'],
  ['running', 'Assessing'],
  ['stopped', 'Stopped: needs correction'],
  ['awaiting_confirmation', 'Awaiting confirmation'],
  ['confirmed', 'Confirmed'],
  ['overridden', 'Overridden'],
]

const DUE = [
  ['', 'Any'],
  ['due_today', 'Due today'],
  ['overdue', 'Overdue'],
]

export default function CaseQueuePage() {
  const [params, setParams] = useSearchParams()
  const view = VIEWS[params.get('view')] ? params.get('view') : ''
  // the due filter lives in the address, so Home's Overdue tile can open the queue filtered
  const due = DUE.some(([v]) => v === params.get('due')) ? params.get('due') : ''
  const setDue = (value) => {
    const next = new URLSearchParams(params)
    if (value) next.set('due', value)
    else next.delete('due')
    setParams(next)
  }
  const [status, setStatus] = useState('')
  const [loan, setLoan] = useState('')
  const [q, setQ] = useState('')
  const filters = { status, loan_type: loan, q: q.trim(), due }
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/cases?${queryOf(filters)}`),
    [status, loan, q, due],
  )

  const shown = data ? data.filter((c) => matchesView(c, view)) : null
  return (
    <div className="queue-page">
      <div className="queue-head">
        <h1>Cases</h1>
        <div className="queue-actions">
          <ExportButton path={`/cases/export.csv?${queryOf(filters, { view })}`}>
            Export CSV
          </ExportButton>
          <Link to="/cases/new" className="btn btn-primary">
            New case
          </Link>
        </div>
      </div>
      <p className="export-note small muted">
        Exports the cases shown, with your filters. No applicant names.
      </p>
      <div className="filters" role="search">
        <div className="field">
          <label htmlFor="q">Search</label>
          <input
            id="q"
            className="input"
            placeholder="Case number or applicant"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="fs">Status</label>
          <select
            id="fs"
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUSES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="fl">Loan type</label>
          <select id="fl" className="select" value={loan} onChange={(e) => setLoan(e.target.value)}>
            <option value="">All loan types</option>
            {LOAN_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="fd">Due</label>
          <select id="fd" className="select" value={due} onChange={(e) => setDue(e.target.value)}>
            {DUE.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>
      {view && (
        <p className="view-note">
          Showing: <strong>{VIEWS[view].label}</strong>{' '}
          <button type="button" className="btn btn-ghost" onClick={() => setParams({})}>
            Show all cases
          </button>
        </p>
      )}
      {loading && !data && <SectionLoader label="Loading cases" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      <div className={loading && data ? 'is-pending' : undefined} aria-busy={loading}>
        {shown && shown.length === 0 && (
          <EmptyState
            title="No cases yet"
            action={
              <Link to="/cases/new" className="btn">
                Start a new case
              </Link>
            }
          >
            Cases you create appear here.
          </EmptyState>
        )}
        {shown && shown.length > 0 && <CaseQueueTable cases={shown} />}
      </div>
    </div>
  )
}
