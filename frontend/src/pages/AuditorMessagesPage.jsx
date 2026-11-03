import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from '../components/Dialog'
import { MessageChip } from './SentItemsPage'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

/** Officers' customer messages, read-only. The recipient is masked; nothing can be sent here. */
export default function AuditorMessagesPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/auditor/messages'), [])
  const [open, setOpen] = useState(null)
  return (
    <div className="aud-page">
      <header>
        <h1>Messages</h1>
        <p className="muted">
          Contact requests officers sent to customers, read-only. Recipient emails are masked.
        </p>
      </header>
      {loading && <Skeleton lines={4} height={36} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && <EmptyState title="No messages">None sent yet.</EmptyState>}
      {data && data.length > 0 && (
        <div className="card aud-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Case</th>
                <th>Officer</th>
                <th>To</th>
                <th>Subject</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <tr key={m.id}>
                  <td data-label="When">{new Date(m.sent_at ?? m.created_at).toLocaleString()}</td>
                  <td data-label="Case" className="mono">
                    {m.case_no}
                  </td>
                  <td data-label="Officer">{m.officer}</td>
                  <td data-label="To">{m.recipient}</td>
                  <td data-label="Subject">
                    <button type="button" className="link-btn" onClick={() => setOpen(m)}>
                      {m.subject}
                    </button>
                  </td>
                  <td data-label="Status">
                    <MessageChip status={m.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <Dialog title="Message" onClose={() => setOpen(null)} labelledBy="aud-msg-title">
          <p className="small muted">
            <span className="mono">{open.case_no}</span> · {open.officer} to {open.recipient}
          </p>
          <pre className="aud-pre">{open.text}</pre>
          {open.block_reason && <p className="small muted">Blocked: {open.block_reason}</p>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setOpen(null)} data-autofocus>
              Close
            </button>
          </div>
        </Dialog>
      )}
    </div>
  )
}
