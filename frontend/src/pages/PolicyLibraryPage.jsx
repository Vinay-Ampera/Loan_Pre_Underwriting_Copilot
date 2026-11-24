import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import FitPanes from '../components/FitPanes'
import { SectionLoader } from '../components/Loading'
import PolicyList from '../components/PolicyList'
import PolicyReader from '../components/PolicyReader'
import PolicySearch from '../components/PolicySearch'
import { ErrorState } from '../components/States'
import { day } from '../lib/policy'
import './PolicyLibraryPage.css'

function Reader({ loanType }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/knowledge/policies/${loanType}`),
    [loanType],
  )
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading && !data) return <SectionLoader label="Loading the policy" />
  if (!data) return null
  return (
    <div className="lib-reader fit-scroll">
      {data.scheduled && (
        <p className="lib-note small">
          A new version, <span className="mono">{data.scheduled.version}</span>, takes effect on{' '}
          {day(data.scheduled.effective_from)}.
        </p>
      )}
      <PolicyReader version={data.active} />
    </div>
  )
}

/** Officer: read the policy in force and search it. Read-only; the admin changes it. */
export default function PolicyLibraryPage() {
  const [loanType, setLoanType] = useState('common')
  const list = useAsync(() => api.get('/knowledge/policies'), [])
  return (
    <div className="lib-page">
      <header className="page-head">
        <h1>Policies</h1>
        <p className="muted">
          The policy in force, clause by clause, with the rules that use each clause. A case is
          checked against the version in force when it starts.
        </p>
      </header>
      <section className="card lib-search" aria-label="Search the policy">
        <PolicySearch />
      </section>
      <FitPanes minWidth={861} className="lib-grid">
        {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
        {list.data && (
          <div className="fit-scroll">
            <PolicyList policies={list.data} selected={loanType} onSelect={setLoanType} />
          </div>
        )}
        <Reader key={loanType} loanType={loanType} />
      </FitPanes>
    </div>
  )
}
