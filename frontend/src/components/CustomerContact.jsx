import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import MessageDialog from './MessageDialog'
import { MessageChip } from '../pages/SentItemsPage'
import './CustomerContact.css'

/** After confirm, override or a stopped run: the officer may send the customer a contact request. */
export default function CustomerContact({ caseId, recipient }) {
  const { data, reload } = useAsync(() => api.get(`/cases/${caseId}/messages`), [caseId])
  const [open, setOpen] = useState(false)

  return (
    <div className="card customer-contact">
      <h3>Contact the customer</h3>
      <p className="small muted">
        Send a short request to get in touch. It never contains case details, a score or a result.
      </p>
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        Write a message
      </button>
      {data && data.length > 0 && (
        <ul className="contact-list" aria-label="Messages for this case">
          {data.slice(0, 3).map((m) => (
            <li key={m.id}>
              <span className="small">
                {new Date(m.sent_at || m.created_at).toLocaleDateString()}
              </span>
              <MessageChip status={m.status} />
            </li>
          ))}
        </ul>
      )}
      {data && data.length > 0 && (
        <Link to="/messages" className="small">
          See all in Sent items
        </Link>
      )}
      {open && (
        <MessageDialog
          caseId={caseId}
          recipient={recipient}
          onClose={() => setOpen(false)}
          onDone={reload}
        />
      )}
    </div>
  )
}
