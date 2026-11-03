import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import StatusChip from '../components/StatusChip'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

const ROLE = { officer: 'Loan officer', admin: 'Admin', auditor: 'Auditor' }

/** The staff list, read-only: name, role, status and last sign-in. No buttons anywhere. */
export default function AuditorUsersPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/auditor/users'), [])
  return (
    <div className="aud-page">
      <header>
        <h1>Users</h1>
        <p className="muted">Staff accounts, read-only.</p>
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
                <th>Role</th>
                <th>Status</th>
                <th>Last sign-in</th>
              </tr>
            </thead>
            <tbody>
              {data.map((u) => (
                <tr key={u.id}>
                  <td data-label="Name">{u.name}</td>
                  <td data-label="Role">{ROLE[u.role] ?? u.role}</td>
                  <td data-label="Status">
                    {u.active ? (
                      u.locked ? (
                        <StatusChip tone="refer">Locked after failed sign-ins</StatusChip>
                      ) : (
                        <StatusChip tone="approve">Active</StatusChip>
                      )
                    ) : (
                      <StatusChip tone="stopped">Disabled</StatusChip>
                    )}
                  </td>
                  <td data-label="Last sign-in">
                    {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
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
