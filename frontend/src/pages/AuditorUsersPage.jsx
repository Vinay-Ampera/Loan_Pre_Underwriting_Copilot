import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import StatusChip from '../components/StatusChip'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

const ROLE = { officer: 'Loan officer', admin: 'Admin', auditor: 'Auditor' }

/** The staff list, read-only: no create, disable or reset. */
export default function AuditorUsersPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/auditor/users'), [])
  return (
    <div className="aud-page">
      <header>
        <h1>Users</h1>
        <p className="muted">Staff accounts, read-only. Emails are masked.</p>
      </header>
      {loading && <Skeleton lines={4} height={36} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && <EmptyState title="No users">None.</EmptyState>}
      {data && data.length > 0 && (
        <div className="card aud-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.map((u) => (
                <tr key={u.id}>
                  <td data-label="Name">{u.name}</td>
                  <td data-label="Email">{u.email}</td>
                  <td data-label="Role">{ROLE[u.role] ?? u.role}</td>
                  <td data-label="Status">
                    {u.active ? (
                      <StatusChip tone="approve">Active</StatusChip>
                    ) : (
                      <StatusChip tone="stopped">Disabled</StatusChip>
                    )}
                  </td>
                  <td data-label="Created">{new Date(u.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
