import './LoanTypePicker.css'

export const LOAN_TYPES = [
  { id: 'personal', label: 'Personal loan', blurb: 'Salaried or self-employed, unsecured' },
  { id: 'home', label: 'Home loan', blurb: 'Purchase; optional co-applicant' },
  { id: 'education', label: 'Education loan', blurb: 'Student with a co-applicant' },
  { id: 'business', label: 'Business loan', blurb: 'GST, ITR and Udyam based' },
  { id: 'vehicle', label: 'Vehicle loan', blurb: 'Car or two-wheeler, new or used' },
]

export const loanLabel = (id) => LOAN_TYPES.find((t) => t.id === id)?.label ?? id

export default function LoanTypePicker({ value, onChange }) {
  return (
    <div className="loan-picker" role="radiogroup" aria-label="Loan type">
      {LOAN_TYPES.map((t) => (
        <button
          key={t.id}
          type="button"
          role="radio"
          aria-checked={value === t.id}
          className={`loan-card card${value === t.id ? ' selected' : ''}`}
          onClick={() => onChange(t.id)}
        >
          <span className="loan-name">{t.label}</span>
          <span className="small muted">{t.blurb}</span>
        </button>
      ))}
    </div>
  )
}
