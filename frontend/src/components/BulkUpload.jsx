import { useRef, useState } from 'react'
import './UploadZone.css'
import './BulkUpload.css'

const ICON = { accepted: '✓', warning: '!', rejected: '✕', ignored: '=' }
const LABEL = {
  accepted: 'Received',
  warning: 'Received with a note',
  rejected: 'Not accepted',
  ignored: 'Repeat, ignored',
}

/** One summary line: "12 received · 1 not accepted · 2 repeats ignored". */
export function summarise(results) {
  const n = (...s) => results.filter((r) => s.includes(r.status)).length
  const parts = [
    [n('accepted', 'warning'), 'received'],
    [n('rejected'), 'not accepted'],
    [n('ignored'), 'repeats ignored'],
  ].filter(([c]) => c > 0)
  return parts.map(([c, t]) => `${c} ${t}`).join(' · ')
}

/**
 * Add a zip, a whole folder or many files in one go. `upload(form)` sends them and returns
 * [{ name, status, message }] (status: accepted | warning | rejected | ignored). The same box
 * serves the officer's desk and the applicant's page. Choosing files needs no confirmation.
 */
export default function BulkUpload({ upload, onUploaded, disabled = false, intro }) {
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [over, setOver] = useState(false)
  const files = useRef(null)
  const folder = useRef(null)

  async function send(list) {
    if (!list.length || disabled) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    // a folder sends each file's path inside it, which the server only uses as a label
    list.forEach((f) => form.append('files', f, f.webkitRelativePath || f.name))
    try {
      const out = await upload(form)
      setResults(out)
      onUploaded?.(out)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
      if (files.current) files.current.value = ''
      if (folder.current) folder.current.value = ''
    }
  }

  return (
    <div className="bulk">
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
        <p>{intro || 'Drop a zip or your files here, or choose them below.'}</p>
        <div className="bulk-buttons">
          <label className={`btn${busy || disabled ? ' disabled' : ''}`} htmlFor="bulk-files">
            {busy ? 'Checking files…' : 'Choose files or a zip'}
          </label>
          <label className={`btn${busy || disabled ? ' disabled' : ''}`} htmlFor="bulk-folder">
            Choose a folder
          </label>
        </div>
        <input
          id="bulk-files"
          ref={files}
          type="file"
          multiple
          className="sr-only"
          accept=".pdf,.jpg,.jpeg,.png,.zip,application/pdf,image/jpeg,image/png,application/zip"
          disabled={busy || disabled}
          onChange={(e) => send([...e.target.files])}
        />
        <input
          id="bulk-folder"
          ref={folder}
          type="file"
          className="sr-only"
          webkitdirectory=""
          multiple
          disabled={busy || disabled}
          onChange={(e) => send([...e.target.files])}
        />
        <p className="small muted">
          PDF, JPG, PNG or a zip of them. Each file up to 10 MB. Password-protected PDFs and very
          blurry photos are not accepted.
        </p>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {results.length > 0 && (
        <div aria-live="polite" data-testid="bulk-results">
          <p className="bulk-summary">
            <strong>{summarise(results)}</strong>
          </p>
          <ul className="upload-results">
            {results.map((r, i) => (
              <li key={`${r.name}-${i}`} className={`ur ur-${r.status}`}>
                <span className="ur-icon" aria-hidden="true">
                  {ICON[r.status]}
                </span>
                <div>
                  <p>
                    <strong>{r.name}</strong> <span className="ur-label">{LABEL[r.status]}</span>
                  </p>
                  {r.message && <p className="small">{r.message}</p>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
