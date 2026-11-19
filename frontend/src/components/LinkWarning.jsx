import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Icon from './Icons'
import './LinkWarning.css'

const OPEN_STATUS = ['draft', 'uploaded', 'applicant_submitted']

/** Does the applicant still owe this case something? Before the first send, or after the officer
 * asked for more and the applicant has not sent again. */
export const applicantOwes = (c) =>
  OPEN_STATUS.includes(c.status) && (!c.applicant_sent || Boolean(c.more_requested))

function Inner({ c }) {
  const { data } = useAsync(() => api.get(`/cases/${c.id}/link`), [c.id, c.more_requested?.at])
  const link = data?.link
  if (!link || link.state === 'active') return null
  const expired = link.state === 'expired'
  return (
    <aside className="link-warning" role="alert">
      <span className="link-warning-icon">
        <Icon name="alert" size={20} />
      </span>
      <div className="link-warning-body">
        <strong>
          The upload link for <span className="mono">{c.case_no}</span> has{' '}
          {expired ? 'expired' : 'been switched off'}
        </strong>
        <p>
          {c.more_requested
            ? 'The applicant was asked for more documents but can no longer add them. '
            : 'The applicant has not sent yet and can no longer add documents. '}
          {expired
            ? 'Open the Upload links page and choose Set days to open it again for as long as you need.'
            : 'A switched-off link cannot be opened again. Use Ask the applicant to make a new one for this case.'}
        </p>
      </div>
      <Link className="btn" to={`/links?case=${encodeURIComponent(c.case_no)}`}>
        Open Upload links
      </Link>
    </aside>
  )
}

/**
 * Shown to the officer on a case whose upload link is no longer open while the applicant still
 * owes documents. It fetches the link only when that could matter.
 */
export default function LinkWarning({ c }) {
  if (!applicantOwes(c)) return null
  return <Inner c={c} />
}
