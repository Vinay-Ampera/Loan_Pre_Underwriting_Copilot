import './AuditTimeline.css'

const LABEL = {
  case_created: 'Case created',
  document_uploaded: 'Document uploaded',
  document_rejected: 'Upload rejected',
  document_removed: 'Document removed',
  case_submitted: 'Submitted for assessment',
  case_resumed_after_fix: 'Resumed after correction',
  pipeline_started: 'Assessment started',
  pipeline_finished: 'Assessment finished',
  pipeline_failed: 'Assessment failed',
  officer_confirm: 'Recommendation confirmed',
  officer_override: 'Recommendation overridden',
  report_exported: 'Report exported to PDF',
}

export default function AuditTimeline({ events }) {
  if (!events.length) return <p className="muted">Nothing recorded yet.</p>
  return (
    <ol className="timeline">
      {events.map((e, i) => (
        <li key={i}>
          <span className="tl-dot" aria-hidden="true" />
          <div>
            <p>
              <strong>{LABEL[e.action] || e.action}</strong>
              {e.detail?.final && (
                <span className="muted"> – final decision: {e.detail.final}</span>
              )}
              {e.detail?.result === 'rejected' && <span className="muted"> – {e.detail.code}</span>}
            </p>
            <p className="small muted">
              {e.actor} · {new Date(e.at).toLocaleString()}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}
