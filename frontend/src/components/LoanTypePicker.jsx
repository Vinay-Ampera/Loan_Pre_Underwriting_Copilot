import ChoiceCard from './ChoiceCard'
import './LoanTypePicker.css'

export const LOAN_TYPES = [
  {
    id: 'personal',
    label: 'Personal loan',
    blurb: 'Salaried or self-employed, unsecured',
    icon: 'wallet',
  },
  { id: 'home', label: 'Home loan', blurb: 'Purchase; optional co-applicant', icon: 'home' },
  { id: 'education', label: 'Education loan', blurb: 'Student with a co-applicant', icon: 'cap' },
  { id: 'business', label: 'Business loan', blurb: 'GST, ITR and Udyam based', icon: 'briefcase' },
  { id: 'vehicle', label: 'Vehicle loan', blurb: 'Car or two-wheeler, new or used', icon: 'car' },
]

export const loanLabel = (id) => LOAN_TYPES.find((t) => t.id === id)?.label ?? id

export default function LoanTypePicker({ value, onChange }) {
  return (
    <div className="loan-picker" role="radiogroup" aria-label="Loan type">
      {LOAN_TYPES.map((t) => (
        <ChoiceCard
          key={t.id}
          icon={t.icon}
          title={t.label}
          checked={value === t.id}
          onSelect={() => onChange(t.id)}
        >
          {t.blurb}
        </ChoiceCard>
      ))}
    </div>
  )
}
