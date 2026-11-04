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
  const [way, setWay] = useState(null) // 'documents' (the desk) | 'form' (type the form first)
  const [starting, setStarting] = useState(false)
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

  async function startDesk() {
    setServerError(null)
    setStarting(true)
    try {
      const res = await api.post('/cases/intake', { loan_type: loanType })
      navigate(`/cases/${res.id}`)
    } catch (e) {
      setServerError(e.message)
      setStarting(false)
    }
  }

  return (
    <div className="new-case">
      <h1>New case</h1>
      <section>
        <h2>1. Loan type</h2>
        <LoanTypePicker
          value={loanType}
          onChange={(t) => {
            setLoanType(t)
            setWay(null)
          }}
        />
      </section>
      {loanType && (
        <section>
          <h2>2. How do you want to start?</h2>
          <div className="way-pick" role="radiogroup" aria-label="How to start">
            <button
              type="button"
              role="radio"
              aria-checked={way === 'documents'}
              className={`loan-card card${way === 'documents' ? ' selected' : ''}`}
              onClick={() => setWay('documents')}
            >
              <span className="loan-name">Start with the documents</span>
              <span className="small muted">
                Upload a zip, a folder or the files. They are sorted and checked, and the identity
                part of the form is filled from the PAN and Aadhaar cards for you to confirm.
              </span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={way === 'form'}
              className={`loan-card card${way === 'form' ? ' selected' : ''}`}
              onClick={() => setWay('form')}
            >
              <span className="loan-name">Fill in the form first</span>
              <span className="small muted">Type everything yourself, then add the documents.</span>
            </button>
          </div>
          {way === 'documents' && (
            <div className="form-actions">
              {serverError && (
                <p className="field-error" role="alert">
                  {serverError}
                </p>
              )}
              <button
                type="button"
                className="btn btn-primary"
                disabled={starting}
                onClick={startDesk}
              >
                {starting ? 'Opening…' : 'Open the case and add documents'}
              </button>
            </div>
          )}
        </section>
      )}
      {loanType && way === 'form' && (
        <section>
          <h2>3. {loanLabel(loanType)} application</h2>
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
