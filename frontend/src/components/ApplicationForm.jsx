import { useState } from 'react'
import './ApplicationForm.css'

const PAN = /^[A-Z]{5}[0-9]{4}[A-Z]$/
const PAN_MASKED = /^[A-Z]{5}\*{4}[A-Z]$/
const PHONE = /^[6-9][0-9]{9}$/
const PHONE_MASKED = /^\*{6}[0-9]{4}$/
const EMAIL = /^[^@\s*]+@[^@\s]+\.[^@\s]+$/
const EMAIL_MASKED = /^\*{4}@[^@\s]+\.[^@\s]+$/

const blankPerson = (role) => ({
  role,
  full_name: '',
  dob: '',
  pan: '',
  aadhaar_last4: '',
  phone: '',
  email: '',
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

/**
 * The five identity fields a PAN or Aadhaar card may fill in. A value is "from documents" only
 * while it is exactly what the card gave; typing over it makes it the officer's own.
 */
export const IDENTITY_FIELDS = ['full_name', 'dob', 'pan', 'aadhaar_last4', 'address']
export function isFromDocument(field, typed, offered) {
  if (offered == null || offered === '' || typed == null || typed === '') return false
  const a = String(typed).trim()
  const b = String(offered).trim()
  return field === 'pan' ? a.toUpperCase() === b.toUpperCase() : a === b
}

/** Rebuild form state for a case opened at the desk: identity from the cards, claims from the
 * applicant's request (if there was one) and the employment the officer stated. Nothing else. */
export function stateFromDesk(c, offer, inventory) {
  const req = c.request || {}
  const employment = Object.fromEntries(
    (inventory?.people || []).map((p) => [p.role, p.employment]),
  )
  const people = {}
  for (const role of c.people || ['primary']) {
    const base = blankPerson(role)
    const earner = req.earner_role === role
    const student = c.loan_type === 'education' && role === 'primary'
    people[role] = {
      ...base,
      ...(offer?.[role]?.values || {}),
      employment_type: student
        ? 'student'
        : employment[role] || (earner && req.employment_type) || 'salaried',
      declared_monthly_income:
        earner && req.declared_monthly_income != null ? String(req.declared_monthly_income) : '',
    }
  }
  return {
    loan_amount: c.loan_amount ?? '',
    tenure_months: c.tenure_months ?? '',
    purpose: c.purpose || '',
    application_date: '',
    details: {},
    people,
  }
}

/** `required` is always passed: a field shows either a * or "(optional)", never neither. */
function Field({ id, label, required, error, hint, tag, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required ? (
          <span className="req" title="Required">
            {' '}
            *
          </span>
        ) : (
          <span className="opt"> (optional)</span>
        )}
        {tag && <span className="from-doc"> from documents</span>}
      </label>
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

function Person({ p, set, errors, editing, prefix, offer }) {
  const idOf = (n) => `${prefix}-${n}`
  // what the cards offered: a tag while the value is still theirs, a note where they could not
  const tagOf = (n) => isFromDocument(n, p[n], offer?.values?.[n])
  const noteOf = (n) => (!p[n] && offer?.notes?.[n]) || undefined
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
      <Field
        id={idOf('full_name')}
        label="Full name (as on PAN)"
        required
        error={errors.full_name}
        tag={tagOf('full_name')}
        hint={noteOf('full_name')}
      >
        <input className="input" {...bind('full_name')} autoComplete="off" />
      </Field>
      <Field
        id={idOf('dob')}
        label="Date of birth"
        required
        error={errors.dob}
        tag={tagOf('dob')}
        hint={noteOf('dob')}
      >
        <input className="input" type="date" {...bind('dob')} />
      </Field>
      <Field
        id={idOf('pan')}
        label="PAN"
        required
        error={errors.pan}
        tag={tagOf('pan')}
        hint={
          editing
            ? 'Shown masked. Leave as it is to keep it, or type the corrected PAN.'
            : noteOf('pan')
        }
      >
        <input className="input mono" {...bind('pan')} maxLength={10} autoComplete="off" />
      </Field>
      <Field
        id={idOf('aadhaar_last4')}
        label="Aadhaar (last four digits)"
        required
        error={errors.aadhaar_last4}
        tag={tagOf('aadhaar_last4')}
        hint={noteOf('aadhaar_last4')}
      >
        <input
          className="input mono"
          {...bind('aadhaar_last4')}
          maxLength={4}
          inputMode="numeric"
          autoComplete="off"
        />
      </Field>
      <Field id={idOf('phone')} label="Mobile number" required={false} error={errors.phone}>
        <input
          className="input mono"
          {...bind('phone')}
          maxLength={10}
          inputMode="numeric"
          autoComplete="off"
        />
      </Field>
      {p.role === 'primary' && (
        <Field
          id={idOf('email')}
          label="Customer email"
          required={false}
          error={errors.email}
          hint="Used only to send the customer a contact request. Never shown to any AI service."
        >
          <input className="input" type="email" {...bind('email')} autoComplete="off" />
        </Field>
      )}
      <Field
        id={idOf('address')}
        label="Address"
        required
        error={errors.address}
        tag={tagOf('address')}
        hint={noteOf('address')}
      >
        <input className="input" {...bind('address')} autoComplete="off" />
      </Field>
      <Field
        id={idOf('employment_type')}
        label="Occupation"
        required
        error={errors.employment_type}
      >
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
            required={false}
            error={errors.employer_or_business}
          >
            <input className="input" {...bind('employer_or_business')} />
          </Field>
          <Field
            id={idOf('declared_monthly_income')}
            label="Declared monthly income (INR)"
            required
            error={errors.declared_monthly_income}
          >
            <input className="input" type="number" min="0" {...bind('declared_monthly_income')} />
          </Field>
          <Field
            id={idOf('months_in_current_employment')}
            label="Months in current job or business"
            required={false}
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
            required={false}
            error={errors.total_experience_months}
          >
            <input className="input" type="number" min="0" {...bind('total_experience_months')} />
          </Field>
        </>
      )}
      <Field id={idOf('residential_status')} label="Residential status" required={false}>
        <select className="select" {...bind('residential_status')}>
          <option value="resident">Resident</option>
          <option value="NRI">NRI</option>
        </select>
      </Field>
      {p.role === 'co' && (
        <Field
          id={idOf('relationship_to_primary')}
          label="Relationship to applicant"
          required={false}
          error={errors.relationship_to_primary}
        >
          <input className="input" {...bind('relationship_to_primary')} />
        </Field>
      )}
    </div>
  )
}

/** A loan-type field is required unless the server marks it optional (yes/no fields always have a value). */
const isRequired = (f) => f.kind !== 'boolean' && f.required !== false

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
      phone: p.phone.trim() || null,
      email: r === 'primary' ? p.email.trim() || null : null,
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
    if (ph && !PHONE.test(ph) && !(editing && PHONE_MASKED.test(ph)))
      e.phone = 'Enter a 10-digit mobile number.'
    const em = p.email.trim()
    if (r === 'primary' && em && !EMAIL.test(em) && !(editing && EMAIL_MASKED.test(em)))
      e.email = 'Enter a valid email address, or leave it empty.'
    if (p.address.trim().length < 5) e.address = 'Enter the address.'
    if (p.employment_type !== 'student' && p.declared_monthly_income === '')
      e.declared_monthly_income = 'Enter the monthly income.'
  }
  for (const f of meta.fields[loanType]) {
    if (isRequired(f) && (s.details[f.name] ?? '') === '')
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
  offer,
  claimNote,
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
  const [tick, setTick] = useState(Boolean(initial?.identityConfirmed))

  const setTop = (n, v) => setS((x) => ({ ...x, [n]: v }))
  const setPerson = (role) => (n, v) =>
    setS((x) => ({ ...x, people: { ...x.people, [role]: { ...x.people[role], [n]: v } } }))
  const setDetail = (n, v) => setS((x) => ({ ...x, details: { ...x.details, [n]: v } }))

  // identity values still exactly as the cards gave them need the officer's tick
  const roles = hasCo ? ['primary', 'co'] : ['primary']
  const fromCards = roles.some((r) =>
    IDENTITY_FIELDS.some((n) => isFromDocument(n, s.people[r][n], offer?.[r]?.values?.[n])),
  )

  async function submit(e) {
    e.preventDefault()
    const { errors, bad } = validate(loanType, meta, s, hasCo, editing)
    if (fromCards && !tick) errors.tick = 'Tick the box to confirm the details read from the cards.'
    setErrs(errors)
    if (bad || errors.tick) return
    setBusy(true)
    try {
      await onSubmit({ ...toBody(loanType, meta, s, hasCo), identity_confirmed: fromCards && tick })
    } finally {
      setBusy(false)
    }
  }

  const e = errs || { top: {}, people: { primary: {}, co: {} }, details: {} }
  return (
    <form className="app-form" onSubmit={submit} noValidate>
      <aside className="form-note" aria-label="How to fill this form">
        <p>
          <strong>*</strong> means required. The case cannot be created without it, and you will see
          a message under the field.
        </p>
        <p>
          <strong>(optional)</strong> can stay empty. Nothing breaks and the score is not changed.
          If you fill one in, the system compares it with the documents.
        </p>
        <p>
          Everything you type here is the applicant&apos;s claim, and the uploaded documents are
          tested against it. Phone, PAN and Aadhaar are masked before any AI service sees them. Use
          synthetic data only. Never enter a real person&apos;s details.
        </p>
        {offer && (
          <p>
            Fields marked <span className="from-doc">from documents</span> were read from the PAN
            and Aadhaar cards. Check them against the cards and tick the box before you save.
            Amount, tenure, purpose, employment, income and contact details are never read from a
            document.
          </p>
        )}
        {claimNote}
      </aside>
      <fieldset className="card">
        <legend>Loan</legend>
        <div className="form-grid">
          <Field id="f-amount" label="Loan amount (INR)" required error={e.top.loan_amount}>
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
          <Field id="f-tenure" label="Tenure (months)" required error={e.top.tenure_months}>
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
          <Field id="f-purpose" label="Purpose" required={false}>
            <input
              id="f-purpose"
              className="input"
              value={s.purpose}
              onChange={(ev) => setTop('purpose', ev.target.value)}
            />
          </Field>
          <Field
            id="f-date"
            label="Application date"
            required={false}
            hint="Leave empty for today."
          >
            <input
              id="f-date"
              className="input"
              type="date"
              value={s.application_date}
              onChange={(ev) => setTop('application_date', ev.target.value)}
            />
          </Field>
          {meta.fields[loanType].map((f) => (
            <Field
              key={f.name}
              id={`d-${f.name}`}
              label={f.label}
              required={isRequired(f)}
              error={e.details[f.name]}
            >
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
          offer={offer?.primary}
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
              offer={offer?.co}
            />
          )}
        </fieldset>
      )}

      {fromCards && (
        <div className="field identity-tick">
          <label className="check-row">
            <input
              type="checkbox"
              checked={tick}
              onChange={(ev) => setTick(ev.target.checked)}
              aria-describedby={e.tick ? 'tick-err' : undefined}
            />
            I confirmed the details marked “from documents” against the cards.
          </label>
          {e.tick && (
            <span className="field-error" id="tick-err">
              {e.tick}
            </span>
          )}
        </div>
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
