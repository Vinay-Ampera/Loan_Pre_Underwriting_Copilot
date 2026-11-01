import './DocumentChecklist.css'

const NAME = {
  pan_card: 'PAN card',
  aadhaar: 'Aadhaar',
  photo: 'Photograph',
  payslip: 'Payslips',
  bank_statement: 'Bank statement',
  form16: 'Form 16',
  itr: 'Income tax return',
}
const pretty = (t) =>
  t
    .split('/')
    .map((p) => NAME[p] || p.replaceAll('_', ' '))
    .join(' or ')
const WHO = { primary: 'Applicant', co: 'Co-applicant' }

/** Required against uploaded, per person. Missing items are amber, with a text mark too. */
export default function DocumentChecklist({ items }) {
  const roles = [...new Set(items.map((i) => i.applicant))]
  return (
    <div className="checklist">
      {roles.map((role) => (
        <div key={role}>
          <h4 className="checklist-who">{WHO[role]}</h4>
          <ul>
            {items
              .filter((i) => i.applicant === role)
              .map((i) => (
                <li key={i.type} className={i.met ? 'met' : 'missing'}>
                  <span className="check-mark" aria-hidden="true">
                    {i.met ? '✓' : '!'}
                  </span>
                  <span>
                    {pretty(i.type)}
                    {i.needed > 1 && (
                      <span className="muted">
                        {' '}
                        ({i.have}/{i.needed})
                      </span>
                    )}
                  </span>
                  <span className="sr-only">{i.met ? 'uploaded' : 'missing'}</span>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
