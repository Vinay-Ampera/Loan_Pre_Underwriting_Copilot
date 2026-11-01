import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import PrecedentReviewCard from '../components/PrecedentReviewCard'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AdminPrecedentsPage.css'

const TABS = [
  ['pending', 'Pending'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
  ['all', 'All'],
]

export default function AdminPrecedentsPage() {
  const [tab, setTab] = useState('pending')
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/admin/precedents?status=${tab}`),
    [tab],
  )

  async function approve(id, until) {
    await api.post(`/admin/precedents/${id}/approve`, { valid_until: until })
    reload()
  }
  async function reject(id, note) {
    await api.post(`/admin/precedents/${id}/reject`, { note: note || null })
    reload()
  }

  return (
    <div className="admin-prec">
      <h1>Precedent queue</h1>
      <p className="muted">
        Officer overrides that passed the automatic hard-rule check. Approve only what should guide
        future borderline cases of the same loan type.
      </p>
      <div className="tabs" role="tablist" aria-label="Precedent status">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            className={`tab${tab === id ? ' on' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && <Skeleton lines={4} height={40} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <EmptyState title="Nothing here">No {tab === 'all' ? '' : tab} precedents.</EmptyState>
      )}
      {data &&
        data.map((p) => (
          <PrecedentReviewCard key={p.id} p={p} onApprove={approve} onReject={reject} />
        ))}
    </div>
  )
}
