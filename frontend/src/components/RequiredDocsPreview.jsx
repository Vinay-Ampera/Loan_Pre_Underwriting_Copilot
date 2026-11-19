import Icon from './Icons'
import { docLabel } from '../lib/docLabels'
import { loanLabel } from './LoanTypePicker'
import './RequiredDocsPreview.css'

// The "when" conditions in the rules file, said as a short note.
const WHEN = {
  'employment_type:salaried': 'If salaried',
  'employment_type:self_employed': 'If self-employed',
  'vehicle_kind:two_wheeler': 'If a two-wheeler',
  'vehicle_kind:car': 'If a car',
  'vehicle_condition:used': 'If used',
  'vehicle_condition:new': 'If new',
}
const whenNote = (when) =>
  when
    ? Object.entries(when)
        .map(([k, v]) => WHEN[`${k}:${v}`] || `If ${String(v).replaceAll('_', ' ')}`)
        .join(', ')
    : null

const CO_NOTE = {
  required: 'A co-applicant is required. They give their own identity documents too.',
  optional: 'A co-applicant is optional. If added, they give their own identity documents too.',
}

function Item({ d }) {
  const name = d.any_of ? d.any_of.map((t) => docLabel(t)).join(' or ') : docLabel(d.type)
  const note = whenNote(d.when)
  return (
    <li className="rdp-item">
      <Icon name="file" size={16} className="rdp-icon" />
      <span className="rdp-name">
        {name}
        {note && <span className="rdp-note">{note}</span>}
      </span>
      {d.min_count > 1 && (
        <span className="rdp-count" title={`At least ${d.min_count}`}>
          {d.min_count}
        </span>
      )}
    </li>
  )
}

function Group({ title, items }) {
  if (!items.length) return null
  return (
    <div className="rdp-group">
      <h3>{title}</h3>
      <ul>
        {items.map((d) => (
          <Item key={`${d.applicant}-${d.type}-${whenNote(d.when)}`} d={d} />
        ))}
      </ul>
    </div>
  )
}

/** The documents a loan type needs, from the rules file, shown before the case is opened. */
export default function RequiredDocsPreview({ loanType, meta }) {
  const docs = loanType && meta?.documents?.[loanType]
  return (
    <aside className="rdp card" aria-labelledby="rdp-title">
      <div className="rdp-head">
        <h2 id="rdp-title">Documents needed</h2>
        {loanType && <p className="rdp-loan">{loanLabel(loanType)}</p>}
      </div>
      {!loanType && <p className="rdp-empty">Choose a loan type to see the documents it needs.</p>}
      {docs && (
        <>
          <Group title="Identity" items={docs.filter((d) => d.kyc)} />
          <Group
            title={loanType === 'education' ? 'Student' : 'Income and loan'}
            items={docs.filter((d) => !d.kyc && d.applicant !== 'co')}
          />
          <Group title="Co-applicant" items={docs.filter((d) => !d.kyc && d.applicant === 'co')} />
          {CO_NOTE[meta.co_applicant?.[loanType]] && (
            <p className="rdp-foot">{CO_NOTE[meta.co_applicant[loanType]]}</p>
          )}
          <p className="rdp-foot">
            A number shows how many are needed, such as months of statements.
          </p>
        </>
      )}
    </aside>
  )
}
