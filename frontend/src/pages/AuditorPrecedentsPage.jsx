import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { loanLabel } from '../components/LoanTypePicker'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

/** Every precedent and where it stands, read-only. Approving is the admin's job. */
export default function AuditorPrecedentsPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/auditor/precedents'), [])
  return (
    <div className="aud-page">
      <header>
        <h1>Precedents</h1>
        <p className="muted">
          Overrides proposed as precedents and the admin&apos;s decision on each. Read-only.
        </p>
      </header>
      {loading && <Skeleton lines={4} height={36} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && <EmptyState title="No precedents">None yet.</EmptyState>}
      {data && data.length > 0 && (
        <div className="card aud-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Loan</th>
                <th>Status</th>
                <th>Recommended</th>
                <th>Final</th>
                <th>Proposed by</th>
                <th>Reviewed by</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td data-label="Case" className="mono">
                    {p.case_no ?? ''}
                  </td>
                  <td data-label="Loan">{loanLabel(p.loan_type)}</td>
                  <td data-label="Status">{p.status}</td>
                  <td data-label="Recommended">{p.original_recommendation}</td>
                  <td data-label="Final">{p.final_decision}</td>
                  <td data-label="Proposed by">{p.proposed_by}</td>
                  <td data-label="Reviewed by">{p.reviewed_by ?? ''}</td>
                  <td data-label="Reason" className="aud-detail small">
                    {p.officer_reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
