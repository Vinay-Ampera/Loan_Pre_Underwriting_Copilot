import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import ApplicationForm from '../components/ApplicationForm'
import ChoiceCard from '../components/ChoiceCard'
import Icon from '../components/Icons'
import LoanTypePicker, { loanLabel } from '../components/LoanTypePicker'
import RequiredDocsPreview from '../components/RequiredDocsPreview'
import { ErrorState, Skeleton } from '../components/States'
import './NewCasePage.css'

function Step({ n, done, title, hint, children }) {
  return (
    <section className="nc-step" aria-labelledby={`nc-step-${n}`}>
      <header className="nc-step-head">
        <span className={`nc-step-no${done ? ' done' : ''}`} aria-hidden="true">
          {done ? <Icon name="check" size={14} /> : n}
        </span>
        <div>
          <h2 id={`nc-step-${n}`}>{title}</h2>
          {hint && <p className="nc-step-hint">{hint}</p>}
        </div>
      </header>
      <div className="nc-step-body">{children}</div>
    </section>
  )
}

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
      <header className="nc-head">
        <h1>New case</h1>
        <p className="muted">
          Choose the loan and how to start. Nothing is saved until you open the case.
        </p>
      </header>

      <Step n={1} done={!!loanType} title="Loan type">
        <LoanTypePicker
          value={loanType}
          onChange={(t) => {
            setLoanType(t)
            setWay(null)
            setServerError(null)
          }}
        />
      </Step>

      <div className="nc-layout">
        <div className="nc-main">
          <Step
            n={2}
            done={!!way}
            title="How do you want to start?"
            hint={loanType ? null : 'Choose a loan type first.'}
          >
            <div className="way-pick" role="radiogroup" aria-label="How to start">
              <ChoiceCard
                icon="upload"
                title="Start with the documents"
                checked={way === 'documents'}
                disabled={!loanType}
                onSelect={() => setWay('documents')}
              >
                Upload a zip, a folder or the files. They are sorted and checked, and the identity
                part of the form is filled from the PAN and Aadhaar cards for you to confirm.
              </ChoiceCard>
              <ChoiceCard
                icon="pencil"
                title="Fill in the form first"
                checked={way === 'form'}
                disabled={!loanType}
                onSelect={() => setWay('form')}
              >
                Type everything yourself, then add the documents.
              </ChoiceCard>
            </div>
            {loanType && way === 'documents' && (
              <div className="nc-go">
                <p className="muted small">
                  Opens an empty {loanLabel(loanType).toLowerCase()} case with the documents desk
                  ready.
                </p>
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
          </Step>

          {loanType && way === 'form' && (
            <Step n={3} title={`${loanLabel(loanType)} application`}>
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
            </Step>
          )}
        </div>

        <div className="nc-rail">
          <RequiredDocsPreview loanType={loanType} meta={meta.data} />
        </div>
      </div>
    </div>
  )
}
