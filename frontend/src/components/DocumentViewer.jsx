import { useEffect, useState } from 'react'
import { api } from '../api/client'
import './DocumentViewer.css'

const FIELD = {
  name: 'Name',
  pan: 'PAN',
  aadhaar: 'Aadhaar',
  dob: 'Date of birth',
}
const label = (n) => FIELD[n] || n.replaceAll('_', ' ')

/** The file on the left (image or PDF), what was read from it on the right. */
export default function DocumentViewer({ caseId, doc, readOnly = false }) {
  const [url, setUrl] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    let made = null
    setUrl(null)
    setError(null)
    if (readOnly || !doc?.id || doc.status !== 'accepted') return undefined
    api
      .blob(`/cases/${caseId}/documents/${doc.id}/file`)
      .then((b) => {
        if (!live) return
        made = URL.createObjectURL(b)
        setUrl(made)
      })
      .catch((e) => live && setError(e.message))
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [caseId, doc?.id, doc?.status, readOnly])

  if (!doc) return <p className="muted">Choose a document to see what was read from it.</p>
  const isPdf = doc.mime === 'application/pdf'
  const review = doc.fields.filter((f) => f.needs_review)

  return (
    <div className="viewer">
      <div className="viewer-file card">
        {readOnly && (
          <p className="muted">
            The auditor does not see the original document, only what was read.
          </p>
        )}
        {error && <p className="field-error">{error}</p>}
        {!readOnly && !url && !error && <div className="skeleton" style={{ height: 320 }} />}
        {url && isPdf && <iframe title={`Document ${doc.name}`} src={url} />}
        {url && !isPdf && <img src={url} alt={`Uploaded document ${doc.name}`} />}
      </div>
      <div className="viewer-fields card">
        <h3>{doc.name}</h3>
        <p className="small muted">
          Read as: <strong>{(doc.doc_type || '').replaceAll('_', ' ')}</strong>
        </p>
        {doc.warnings.length > 0 && (
          <p className="small warn">
            Image quality warning: {doc.warnings.join(', ').replaceAll('_', ' ')}.
          </p>
        )}
        {doc.fields.length === 0 ? (
          <p className="muted">
            Nothing has been read from this file yet. Fields appear after assessment.
          </p>
        ) : (
          <>
            {review.length > 0 && (
              <p className="small warn">
                {review.length} field(s) read with low confidence. Please verify against the
                document.
              </p>
            )}
            <dl className="fields">
              {doc.fields.map((f) => (
                <div key={f.name} className={f.needs_review ? 'low' : ''}>
                  <dt>{label(f.name)}</dt>
                  <dd>
                    <span className="mono">{f.value}</span>
                    {f.needs_review && <span className="low-tag"> ! Low confidence</span>}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </div>
    </div>
  )
}
