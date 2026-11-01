import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import ApplicationForm from '../components/ApplicationForm'
import LoanTypePicker, { loanLabel } from '../components/LoanTypePicker'
import { ErrorState, Skeleton } from '../components/States'
import './NewCasePage.css'

export default function NewCasePage() {
  const navigate = useNavigate()
  const [loanType, setLoanType] = useState(null)
  const [serverError, setServerError] = useState(null)
  const meta = useAsync(() => api.get('/meta/loan-types'), [])

  async function create(body) {
    setServerError(null)
    try {
      const res = await api.post('/cases', body)
      navigate(`/cases/${res.id}`)
    } catch (e) {
      setServerError(e.message)
    }
  }

  return (
    <div className="new-case">
      <h1>New case</h1>
      <section>
        <h2>1. Loan type</h2>
        <LoanTypePicker value={loanType} onChange={setLoanType} />
      </section>
      {loanType && (
        <section>
          <h2>2. {loanLabel(loanType)} application</h2>
          {meta.loading && <Skeleton lines={4} />}
          {meta.error && <ErrorState error={meta.error} onRetry={meta.reload} />}
          {meta.data && (
            <ApplicationForm
              key={loanType}
              loanType={loanType}
              meta={meta.data}
              submitLabel="Create case and add documents"
              onSubmit={create}
              serverError={serverError}
            />
          )}
        </section>
      )}
    </div>
  )
}
