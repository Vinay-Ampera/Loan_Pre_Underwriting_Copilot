import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import CaseQueueTable from '../components/CaseQueueTable'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { LOAN_TYPES } from '../components/LoanTypePicker'
import './CaseQueuePage.css'

const STATUSES = [
  ['', 'All statuses'],
  ['draft', 'Draft'],
  ['uploaded', 'Documents uploaded'],
  ['running', 'Assessing'],
  ['stopped', 'Stopped: needs correction'],
  ['awaiting_confirmation', 'Awaiting confirmation'],
  ['confirmed', 'Confirmed'],
  ['overridden', 'Overridden'],
]

export default function CaseQueuePage() {
  const [status, setStatus] = useState('')
  const [loan, setLoan] = useState('')
  const [q, setQ] = useState('')
  const { data, error, loading, reload } = useAsync(() => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (loan) p.set('loan_type', loan)
    if (q.trim()) p.set('q', q.trim())
    return api.get(`/cases?${p}`)
  }, [status, loan, q])

  return (
    <div className="queue-page">
      <div className="queue-head">
        <h1>Cases</h1>
        <Link to="/cases/new" className="btn btn-primary">
          New case
        </Link>
      </div>
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
      </div>
      {loading && <Skeleton lines={5} height={36} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
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
      {data && data.length > 0 && <CaseQueueTable cases={data} />}
    </div>
  )
}
