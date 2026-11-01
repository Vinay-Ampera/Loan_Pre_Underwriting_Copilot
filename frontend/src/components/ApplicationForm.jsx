import { useState } from 'react'
import './ApplicationForm.css'

const PAN = /^[A-Z]{5}[0-9]{4}[A-Z]$/
const PAN_MASKED = /^[A-Z]{5}\*{4}[A-Z]$/
const PHONE = /^[6-9][0-9]{9}$/
const PHONE_MASKED = /^\*{6}[0-9]{4}$/

const blankPerson = (role) => ({
  role,
  full_name: '',
  dob: '',
  pan: '',
  aadhaar_last4: '',
  phone: '',
  address: '',
  employment_type: role === 'co' ? 'salaried' : 'salaried',
  employer_or_business: '',
  declared_monthly_income: '',
  relationship_to_primary: role === 'co' ? 'parent' : '',
  residential_status: 'resident',
  months_in_current_employment: '',
  total_experience_months: '',
})

/** Rebuild form state from a case being corrected. PAN and phone come back masked. */
export function stateFromCase(c) {
  const person = (a) => ({
    ...blankPerson(a.role),
    ...Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v ?? ''])),
    aadhaar_last4: (a.aadhaar || '').slice(-4),
  })
  const people = Object.fromEntries(c.applicants.map((a) => [a.role, person(a)]))
  return {
    loan_amount: c.loan_amount,
    tenure_months: c.tenure_months,
    purpose: c.purpose || '',
    application_date: '',
    details: c.loan_details || {},
    people,
  }
}

function Field({ id, label, error, hint, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && <span className="small muted">{hint}</span>}
      {error && (
        <span className="field-error" id={`${id}-err`}>
          {error}
        </span>
      )}
    </div>
  )
}

function Person({ p, set, errors, editing, prefix }) {
  const idOf = (n) => `${prefix}-${n}`
  const bind = (n) => ({
    id: idOf(n),
    value: p[n],
    onChange: (e) => set(n, e.target.value),
    'aria-invalid': Boolean(errors[n]),
    'aria-describedby': errors[n] ? `${idOf(n)}-err` : undefined,
  })
  const student = p.employment_type === 'student'
  return (
    <div className="form-grid">
      <Field id={idOf('full_name')} label="Full name (as on PAN)" error={errors.full_name}>
        <input className="input" {...bind('full_name')} autoComplete="off" />
      </Field>
      <Field id={idOf('dob')} label="Date of birth" error={errors.dob}>
        <input className="input" type="date" {...bind('dob')} />
      </Field>
      <Field
        id={idOf('pan')}
        label="PAN"
        error={errors.pan}
        hint={
          editing
            ? 'Shown masked. Leave as it is to keep it, or type the corrected PAN.'
            : undefined
        }
      >
        <input className="input mono" {...bind('pan')} maxLength={10} autoComplete="off" />
      </Field>
      <Field
        id={idOf('aadhaar_last4')}
        label="Aadhaar (last four digits)"
        error={errors.aadhaar_last4}
      >
        <input
          className="input mono"
          {...bind('aadhaar_last4')}
          maxLength={4}
          inputMode="numeric"
          autoComplete="off"
        />
      </Field>
      <Field id={idOf('phone')} label="Mobile number" error={errors.phone}>
        <input
          className="input mono"
          {...bind('phone')}
          maxLength={10}
          inputMode="numeric"
          autoComplete="off"
        />
      </Field>
      <Field id={idOf('address')} label="Address" error={errors.address}>
        <input className="input" {...bind('address')} autoComplete="off" />
      </Field>
      <Field id={idOf('employment_type')} label="Occupation" error={errors.employment_type}>
        <select className="select" {...bind('employment_type')}>
          <option value="salaried">Salaried</option>
          <option value="self_employed">Self-employed</option>
          <option value="student">Student</option>
        </select>
      </Field>
      {!student && (
        <>
          <Field
            id={idOf('employer_or_business')}
            label="Employer or business"
            error={errors.employer_or_business}
          >
            <input className="input" {...bind('employer_or_business')} />
          </Field>
          <Field
            id={idOf('declared_monthly_income')}
            label="Declared monthly income (INR)"
            error={errors.declared_monthly_income}
          >
            <input className="input" type="number" min="0" {...bind('declared_monthly_income')} />
          </Field>
          <Field
            id={idOf('months_in_current_employment')}
            label="Months in current job or business"
            error={errors.months_in_current_employment}
          >
            <input
              className="input"
              type="number"
              min="0"
              {...bind('months_in_current_employment')}
            />
          </Field>
          <Field
            id={idOf('total_experience_months')}
            label="Total experience (months)"
            error={errors.total_experience_months}
          >
            <input className="input" type="number" min="0" {...bind('total_experience_months')} />
          </Field>
        </>
      )}
      <Field id={idOf('residential_status')} label="Residential status">
        <select className="select" {...bind('residential_status')}>
          <option value="resident">Resident</option>
          <option value="NRI">NRI</option>
        </select>
      </Field>
      {p.role === 'co' && (
        <Field
          id={idOf('relationship_to_primary')}
          label="Relationship to applicant"
          error={errors.relationship_to_primary}
        >
          <input className="input" {...bind('relationship_to_primary')} />
        </Field>
      )}
    </div>
  )
}

function toBody(loanType, meta, s, hasCo) {
  const num = (v) => (v === '' || v == null ? null : Number(v))
  const roles = hasCo ? ['primary', 'co'] : ['primary']
  const applicants = roles.map((r) => {
    const p = s.people[r]
    const student = p.employment_type === 'student'
    return {
      role: r,
      full_name: p.full_name.trim(),
      dob: p.dob,
      pan: p.pan.trim().toUpperCase(),
      aadhaar_last4: p.aadhaar_last4.trim(),
      address: p.address.trim(),
      phone: p.phone.trim(),
      employment_type: p.employment_type,
      employer_or_business: student ? null : p.employer_or_business.trim() || null,
      declared_monthly_income: student ? null : num(p.declared_monthly_income),
      relationship_to_primary: r === 'co' ? p.relationship_to_primary.trim() || null : null,
      residential_status: p.residential_status,
      months_in_current_employment: student ? null : num(p.months_in_current_employment),
      total_experience_months: student ? null : num(p.total_experience_months),
    }
  })
  const details = {}
  for (const f of meta.fields[loanType]) {
    const v = s.details[f.name]
    if (f.kind === 'boolean') details[f.name] = Boolean(v)
    else if (f.kind === 'number') details[f.name] = num(v)
    else details[f.name] = v ?? ''
  }
  return {
    loan_type: loanType,
    loan_amount: num(s.loan_amount),
    tenure_months: num(s.tenure_months),
    purpose: s.purpose.trim() || null,
    application_date: s.application_date || null,
    loan_details: details,
    applicants,
  }
}

function validate(loanType, meta, s, hasCo, editing) {
  const errors = { top: {}, people: { primary: {}, co: {} }, details: {} }
  if (!(Number(s.loan_amount) > 0)) errors.top.loan_amount = 'Enter the loan amount.'
  if (!(Number(s.tenure_months) > 0)) errors.top.tenure_months = 'Enter the tenure in months.'
  for (const r of hasCo ? ['primary', 'co'] : ['primary']) {
    const p = s.people[r]
    const e = errors.people[r]
    if (p.full_name.trim().length < 2) e.full_name = 'Enter the full name.'
    if (!p.dob) e.dob = 'Enter the date of birth.'
    const pan = p.pan.trim().toUpperCase()
    if (!PAN.test(pan) && !(editing && PAN_MASKED.test(pan))) e.pan = 'PAN looks like ABCDE1234F.'
    if (!/^[0-9]{4}$/.test(p.aadhaar_last4.trim())) e.aadhaar_last4 = 'Enter four digits.'
    const ph = p.phone.trim()
    if (!PHONE.test(ph) && !(editing && PHONE_MASKED.test(ph)))
      e.phone = 'Enter a 10-digit mobile number.'
    if (p.address.trim().length < 5) e.address = 'Enter the address.'
    if (p.employment_type !== 'student' && p.declared_monthly_income === '')
      e.declared_monthly_income = 'Enter the monthly income.'
  }
  for (const f of meta.fields[loanType]) {
    if (f.kind !== 'boolean' && (s.details[f.name] ?? '') === '')
      errors.details[f.name] = `Enter ${f.label.toLowerCase()}.`
  }
  const bad =
    Object.keys(errors.top).length ||
    Object.values(errors.people).some((e) => Object.keys(e).length) ||
    Object.keys(errors.details).length
  return { errors, bad }
}

/** Common fields, the loan-specific section, and the co-applicant section where the loan allows it. */
export default function ApplicationForm({
  loanType,
  meta,
  initial,
  editing = false,
  submitLabel,
  onSubmit,
  serverError,
}) {
  const rule = meta.co_applicant[loanType]
  const [s, setS] = useState(
    initial || {
      loan_amount: '',
      tenure_months: '',
      purpose: '',
      application_date: '',
      details: {},
      people: { primary: blankPerson('primary'), co: blankPerson('co') },
    },
  )
  const [hasCo, setHasCo] = useState(
    rule === 'required' || Boolean(initial?.people?.co && initial.people.co.full_name),
  )
  const [errs, setErrs] = useState(null)
  const [busy, setBusy] = useState(false)

  const setTop = (n, v) => setS((x) => ({ ...x, [n]: v }))
  const setPerson = (role) => (n, v) =>
    setS((x) => ({ ...x, people: { ...x.people, [role]: { ...x.people[role], [n]: v } } }))
  const setDetail = (n, v) => setS((x) => ({ ...x, details: { ...x.details, [n]: v } }))

  async function submit(e) {
    e.preventDefault()
    const { errors, bad } = validate(loanType, meta, s, hasCo, editing)
    setErrs(errors)
    if (bad) return
    setBusy(true)
    try {
      await onSubmit(toBody(loanType, meta, s, hasCo))
    } finally {
      setBusy(false)
    }
  }

  const e = errs || { top: {}, people: { primary: {}, co: {} }, details: {} }
  return (
    <form className="app-form" onSubmit={submit} noValidate>
      <fieldset className="card">
        <legend>Loan</legend>
        <div className="form-grid">
          <Field id="f-amount" label="Loan amount (INR)" error={e.top.loan_amount}>
            <input
              id="f-amount"
              className="input"
              type="number"
              min="0"
              value={s.loan_amount}
              onChange={(ev) => setTop('loan_amount', ev.target.value)}
              aria-invalid={Boolean(e.top.loan_amount)}
            />
          </Field>
          <Field id="f-tenure" label="Tenure (months)" error={e.top.tenure_months}>
            <input
              id="f-tenure"
              className="input"
              type="number"
              min="1"
              value={s.tenure_months}
              onChange={(ev) => setTop('tenure_months', ev.target.value)}
              aria-invalid={Boolean(e.top.tenure_months)}
            />
          </Field>
          <Field id="f-purpose" label="Purpose">
            <input
              id="f-purpose"
              className="input"
              value={s.purpose}
              onChange={(ev) => setTop('purpose', ev.target.value)}
            />
          </Field>
          <Field id="f-date" label="Application date" hint="Leave empty for today.">
            <input
              id="f-date"
              className="input"
              type="date"
              value={s.application_date}
              onChange={(ev) => setTop('application_date', ev.target.value)}
            />
          </Field>
          {meta.fields[loanType].map((f) => (
            <Field key={f.name} id={`d-${f.name}`} label={f.label} error={e.details[f.name]}>
              {f.kind === 'select' ? (
                <select
                  id={`d-${f.name}`}
                  className="select"
                  value={s.details[f.name] ?? ''}
                  onChange={(ev) => setDetail(f.name, ev.target.value)}
                >
                  <option value="">Choose…</option>
                  {f.options.map((o) => (
                    <option key={o} value={o}>
                      {o.replaceAll('_', ' ')}
                    </option>
                  ))}
                </select>
              ) : f.kind === 'boolean' ? (
                <select
                  id={`d-${f.name}`}
                  className="select"
                  value={s.details[f.name] ? 'yes' : 'no'}
                  onChange={(ev) => setDetail(f.name, ev.target.value === 'yes')}
                >
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </select>
              ) : (
                <input
                  id={`d-${f.name}`}
                  className="input"
                  type={f.kind === 'number' ? 'number' : 'text'}
                  min={f.kind === 'number' ? 0 : undefined}
                  value={s.details[f.name] ?? ''}
                  onChange={(ev) => setDetail(f.name, ev.target.value)}
                  aria-invalid={Boolean(e.details[f.name])}
                />
              )}
            </Field>
          ))}
        </div>
      </fieldset>

      <fieldset className="card">
        <legend>Applicant</legend>
        <Person
          p={s.people.primary}
          set={setPerson('primary')}
          errors={e.people.primary}
          editing={editing}
          prefix="p"
        />
      </fieldset>

      {rule !== 'not_allowed' && (
        <fieldset className="card">
          <legend>Co-applicant</legend>
          {rule === 'optional' && (
            <label className="check-row">
              <input
                type="checkbox"
                checked={hasCo}
                onChange={(ev) => setHasCo(ev.target.checked)}
              />
              Add a co-applicant
            </label>
          )}
          {rule === 'required' && (
            <p className="muted">A co-applicant is required for this loan.</p>
          )}
          {hasCo && (
            <Person
              p={s.people.co}
              set={setPerson('co')}
              errors={e.people.co}
              editing={editing}
              prefix="c"
            />
          )}
        </fieldset>
      )}

      {serverError && (
        <p className="field-error" role="alert">
          {serverError}
        </p>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
