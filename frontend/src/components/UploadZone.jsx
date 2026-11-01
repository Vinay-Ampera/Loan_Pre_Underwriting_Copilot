import { useRef, useState } from 'react'
import { api } from '../api/client'
import './UploadZone.css'

const ICON = { accepted: '✓', warning: '!', rejected: '✕' }
const LABEL = { accepted: 'Accepted', warning: 'Accepted with a warning', rejected: 'Rejected' }
const TYPE_NAME = { pan_card: 'PAN card', aadhaar: 'Aadhaar', photo: 'Photograph', other: 'Other' }

/** Pick the person and the kind, then add one file or many. Every file gets its own result. */
export default function UploadZone({ caseId, roles, docTypes, onUploaded, disabled }) {
  const [role, setRole] = useState(roles[0])
  const [kind, setKind] = useState('other')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [over, setOver] = useState(false)
  const input = useRef(null)

  async function send(files) {
    if (!files.length || disabled) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    form.append('role', role)
    form.append('doc_type', kind)
    files.forEach((f) => form.append('files', f))
    try {
      const res = await api.upload(`/cases/${caseId}/documents`, form)
      setResults(res.results)
      onUploaded()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="upload">
      <div className="upload-pickers">
        {roles.length > 1 && (
          <div className="field">
            <label htmlFor="up-role">Whose document</label>
            <select
              id="up-role"
              className="select"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {roles.map((r) => (
                <option key={r} value={r}>
                  {r === 'primary' ? 'Applicant' : 'Co-applicant'}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="up-kind">Document type</label>
          <select
            id="up-kind"
            className="select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            {docTypes.map((t) => (
              <option key={t} value={t}>
                {TYPE_NAME[t] || t.replaceAll('_', ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div
        className={`dropzone${over ? ' over' : ''}${disabled ? ' off' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          send([...e.dataTransfer.files])
        }}
      >
        <p>Drop PDF, JPG or PNG files here, or</p>
        <label className={`btn${busy || disabled ? ' disabled' : ''}`} htmlFor="up-files">
          {busy ? 'Checking files…' : 'Choose files'}
        </label>
        <input
          id="up-files"
          ref={input}
          type="file"
          multiple
          className="sr-only"
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          disabled={busy || disabled}
          onChange={(e) => send([...e.target.files])}
        />
        <p className="small muted">
          Password-protected PDFs and blurry photos are rejected. Up to 10 MB each.
        </p>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {results.length > 0 && (
        <ul className="upload-results" aria-live="polite" data-testid="upload-results">
          {results.map((r) => (
            <li key={r.id} className={`ur ur-${r.status}`}>
              <span className="ur-icon" aria-hidden="true">
                {ICON[r.status]}
              </span>
              <div>
                <p>
                  <strong>{r.name}</strong> <span className="ur-label">{LABEL[r.status]}</span>
                </p>
                <p className="small">{r.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
