import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { downloadFile, queryOf } from '../lib/download'
import { LOAN_TYPES, loanLabel } from '../components/LoanTypePicker'
import { CaseStatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

const PAGE = 100
const STATUSES = [
  ['draft', 'Draft'],
  ['uploaded', 'Documents uploaded'],
  ['running', 'Assessing'],
  ['stopped', 'Stopped'],
  ['awaiting_confirmation', 'Awaiting confirmation'],
  ['confirmed', 'Confirmed'],
  ['overridden', 'Overridden'],
]
const BANDS = [
  ['approve', 'Recommend approve'],
  ['refer', 'Refer'],
  ['reject', 'Recommend reject'],
]
const NONE = {
  q: '',
  status: '',
  loan_type: '',
  band: '',
  officer: '',
  overridden: '',
  date_from: '',
  date_to: '',
}
const DECISION = { confirm: 'Confirmed', override: 'Overridden' }
const day = (v) => new Date(v).toLocaleDateString()

function Select({ id, label, value, onChange, all, options }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  )
}

/**
 * One static row per case: reference, loan type, officer, status, band, score, who decided what
 * and when. No applicant, document or report content, and no way into a case.
 */
export default function AuditorCasesPage() {
  const [params] = useSearchParams()
  const [filter, setFilter] = useState({
    ...NONE,
    status: STATUSES.some(([k]) => k === params.get('status')) ? params.get('status') : '',
    overridden: ['officer', 'admin'].includes(params.get('overridden'))
      ? params.get('overridden')
      : '',
  })
  const [page, setPage] = useState(0)
  const [exportError, setExportError] = useState(null)
  const users = useAsync(() => api.get('/auditor/users'), [])
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/auditor/cases?${queryOf(filter, { limit: PAGE, offset: page * PAGE })}`),
    [filter, page],
  )
  const set = (patch) => {
    setFilter((f) => ({ ...f, ...patch }))
    setPage(0)
  }
  const officers = (users.data ?? []).filter((u) => u.role === 'officer').map((u) => [u.id, u.name])
  const filtered = Object.values(filter).some(Boolean)
  async function exportCsv() {
    setExportError(null)
    try {
      await downloadFile(`/auditor/cases.csv?${queryOf(filter)}`, 'cases.csv')
    } catch (e) {
      setExportError(e.message)
    }
  }
  return (
    <div className="aud-page">
      <header>
        <h1>Cases</h1>
        <p className="muted">
          How many cases are in which state, and who decided them. A static table: no applicant
          details, documents or reports.
        </p>
      </header>
      <div className="card aud-filters" role="search">
        <div className="field">
          <label htmlFor="ac-q">Case reference</label>
          <input
            id="ac-q"
            className="input"
            type="search"
            placeholder="CASE-2026-0003"
            value={filter.q}
            onChange={(e) => set({ q: e.target.value })}
          />
        </div>
        <Select
          id="ac-status"
          label="Status"
          value={filter.status}
          onChange={(status) => set({ status })}
          all="All statuses"
          options={STATUSES}
        />
        <Select
          id="ac-loan"
          label="Loan type"
          value={filter.loan_type}
          onChange={(loan_type) => set({ loan_type })}
          all="All loan types"
          options={LOAN_TYPES.map((t) => [t.id, t.label])}
        />
        <Select
          id="ac-band"
          label="Recommendation"
          value={filter.band}
          onChange={(band) => set({ band })}
          all="Any recommendation"
          options={BANDS}
        />
        <Select
          id="ac-officer"
          label="Officer"
          value={filter.officer}
          onChange={(officer) => set({ officer })}
          all="All officers"
          options={officers}
        />
        <Select
          id="ac-over"
          label="Changed"
          value={filter.overridden}
          onChange={(overridden) => set({ overridden })}
          all="Any"
          options={[
            ['officer', 'Overridden by the officer'],
            ['admin', 'Changed by an admin'],
          ]}
        />
        <div className="field">
          <label htmlFor="ac-from">Created from</label>
          <input
            id="ac-from"
            className="input"
            type="date"
            value={filter.date_from}
            max={filter.date_to || undefined}
            onChange={(e) => set({ date_from: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="ac-to">to</label>
          <input
            id="ac-to"
            className="input"
            type="date"
            value={filter.date_to}
            min={filter.date_from || undefined}
            onChange={(e) => set({ date_to: e.target.value })}
          />
        </div>
        <button type="button" className="btn" disabled={!filtered} onClick={() => set(NONE)}>
          Clear filters
        </button>
        <button type="button" className="btn" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      {exportError && (
        <p className="field-error" role="alert">
          {exportError}
        </p>
      )}
      {loading && <Skeleton lines={5} height={32} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.rows.length === 0 && <EmptyState title="No cases">No cases match.</EmptyState>}
      {data && data.rows.length > 0 && (
        <>
          <div className="card aud-wrap">
            <table className="aud-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Loan type</th>
                  <th>Officer</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Officer decision</th>
                  <th>Changed by an admin</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.case_no}>
                    <td data-label="Case" className="mono">
                      {r.case_no}
                    </td>
                    <td data-label="Loan type">{loanLabel(r.loan_type)}</td>
                    <td data-label="Officer">{r.officer}</td>
                    <td data-label="Status">
                      <CaseStatusChip status={r.status} band={r.band} />
                    </td>
                    <td data-label="Score">{r.score ?? <span className="muted">–</span>}</td>
                    <td data-label="Officer decision">
                      {DECISION[r.officer_decision] ?? <span className="muted">–</span>}
                    </td>
                    <td data-label="Changed by an admin">{r.admin_corrected ? 'Yes' : 'No'}</td>
                    <td data-label="Created">{day(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="aud-pager">
            <button
              type="button"
              className="btn"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Newer
            </button>
            <span className="small muted">
              {page * PAGE + 1} to {page * PAGE + data.rows.length} of {data.total}
            </span>
            <button
              type="button"
              className="btn"
              disabled={(page + 1) * PAGE >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Older
            </button>
          </div>
        </>
      )}
    </div>
  )
}
