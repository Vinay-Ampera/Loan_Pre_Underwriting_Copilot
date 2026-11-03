import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import StatusChip, { CaseStatusChip } from '../components/StatusChip'
import { loanLabel } from '../components/LoanTypePicker'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AdminOfficerPage.css'

const STATUS = [
  ['draft', 'Draft'],
  ['uploaded', 'Uploaded'],
  ['running', 'Assessing'],
  ['stopped', 'Stopped'],
  ['awaiting_confirmation', 'Awaiting confirmation'],
  ['confirmed', 'Confirmed'],
  ['overridden', 'Overridden'],
]
const BAND = [
  ['approve', 'Recommended approve'],
  ['refer', 'Refer'],
  ['reject', 'Recommended reject'],
]
const PRECEDENT = ['pending', 'approved', 'rejected', 'held', 'expired']
// cases the officer has not decided and that are not running: the ones an admin can reassign
const OPEN = ['draft', 'uploaded', 'stopped', 'awaiting_confirmation']
const FILTERS = [
  ['', 'All cases', () => true],
  ['open', 'Not decided by the officer', (c) => OPEN.includes(c.status)],
  ...STATUS.map(([k, l]) => [k, l, (c) => c.status === k]),
  ['corrected', 'Changed by an admin', (c) => c.corrected],
]
const when = (v) => (v ? new Date(v).toLocaleString() : 'Never')
const money = (n) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(n)

function Counts({ title, rows }) {
  return (
    <section className="card officer-block">
      <h2>{title}</h2>
      <ul className="officer-counts">
        {rows.map(([label, n]) => (
          <li key={label}>
            <span className="officer-n">{n}</span> <span className="muted">{label}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** An officer's profile for the admin: counts, and every case the officer owns, openable. */
export default function AdminOfficerPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const filter = FILTERS.some(([k]) => k === params.get('status')) ? params.get('status') : ''
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/admin/users/${id}/activity`),
    [id],
  )
  const test = FILTERS.find(([k]) => k === filter)[2]
  const shown = data ? data.cases.filter(test) : []
  return (
    <div className="officer-page">
      <Link to="/admin/users">← Users</Link>
      {loading && <Skeleton lines={4} height={48} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          <header>
            <h1>{data.user.name}</h1>
            <p className="muted">
              {data.user.email} · {data.user.role} · {data.user.active ? 'Active' : 'Disabled'} ·
              Last sign-in: {when(data.last_login)}
            </p>
          </header>
          <div className="officer-grid">
            <Counts
              title={`Cases (${data.cases_total})`}
              rows={STATUS.map(([k, l]) => [l, data.cases_by_status[k] ?? 0])}
            />
            <Counts
              title="Recommendations"
              rows={BAND.map(([k, l]) => [l, data.cases_by_band[k] ?? 0])}
            />
            <Counts
              title="Decisions"
              rows={[
                ['Confirmed by the officer', data.confirmed],
                ['Overridden by the officer', data.overridden],
                ['Changed by an admin', data.admin_corrected],
              ]}
            />
            <Counts
              title="Precedents proposed"
              rows={PRECEDENT.map((k) => [k, data.precedents_by_status[k] ?? 0])}
            />
          </div>
          <section className="card officer-block">
            <div className="officer-cases-head">
              <h2>Cases</h2>
              <div className="field officer-filter">
                <label htmlFor="officer-status">Show</label>
                <select
                  id="officer-status"
                  className="select"
                  value={filter}
                  onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}
                >
                  {FILTERS.map(([k, l]) => (
                    <option key={k} value={k}>
                      {l}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {data.cases.length === 0 ? (
              <p className="muted">No cases yet.</p>
            ) : shown.length === 0 ? (
              <EmptyState title="No cases match">Choose another filter.</EmptyState>
            ) : (
              <table className="officer-cases">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Applicant</th>
                    <th>Loan</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((c) => (
                    <tr key={c.id}>
                      <td data-label="Case">
                        <Link to={`/cases/${c.id}`} className="mono">
                          {c.case_no}
                        </Link>
                      </td>
                      <td data-label="Applicant">{c.applicant}</td>
                      <td data-label="Loan">
                        {loanLabel(c.loan_type)}{' '}
                        <span className="muted">{money(c.loan_amount)}</span>
                      </td>
                      <td data-label="Status">
                        <CaseStatusChip status={c.status} band={c.band} />{' '}
                        {c.corrected && <StatusChip tone="refer">Changed by an admin</StatusChip>}
                      </td>
                      <td data-label="Updated">{when(c.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  )
}
