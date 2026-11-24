import { useEffect, useRef, useState } from 'react'
import Icon from './Icons'
import Loader from './Loader'
import Toast from './Toast'
import './UploadZone.css'
import './BulkUpload.css'

const ICON = {
  accepted: 'check',
  warning: 'alert-circle',
  rejected: 'x',
  ignored: 'copy',
  bundle: 'alert-circle',
}
const LABEL = {
  accepted: 'Received',
  warning: 'Received with a note',
  rejected: 'Not accepted',
  ignored: 'Repeat, ignored',
  bundle: 'Several documents, check the split',
}

/** One summary line: "12 received · 1 not accepted · 2 repeats ignored". */
export function summarise(results) {
  const n = (...s) => results.filter((r) => s.includes(r.status)).length
  const parts = [
    [n('accepted', 'warning'), 'received'],
    [n('rejected'), 'not accepted'],
    [n('ignored'), 'repeats ignored'],
    [n('bundle'), 'to split'],
  ].filter(([c]) => c > 0)
  return parts.map(([c, t]) => `${c} ${t}`).join(' · ')
}

const sizeOf = (bytes) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`

/** What the officer sees while a zip, a folder or many files are being sent and read. */
function Working({ sending }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])
  const what = sending.zip
    ? 'your zip'
    : `${sending.count} ${sending.count === 1 ? 'file' : 'files'}`
  return (
    <div className="bulk-working" data-testid="bulk-working">
      <Loader label={`Uploading ${what} (${sizeOf(sending.bytes)}) and reading the documents`} />
      <p className="small muted">
        Each file is checked and identified. A zip or a folder can take a minute. Please keep this
        page open{seconds >= 3 ? ` · ${seconds} s` : ''}.
      </p>
    </div>
  )
}

function ResultRows({ rows }) {
  return (
    <ul className="upload-results">
      {rows.map((r, i) => (
        <li key={`${r.name}-${i}`} className={`ur ur-${r.status}`}>
          <span className="ur-icon" aria-hidden="true">
            <Icon name={ICON[r.status]} size={16} />
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
  )
}

/**
 * Add a zip, a whole folder or many files in one go. `upload(form)` sends them and returns
 * [{ name, status, message }] (status: accepted | warning | rejected | ignored | bundle). The same box
 * serves the officer's desk and the applicant's page. Choosing files needs no confirmation.
 * `compact` draws the box as one slim bar (the desk, once files are in); `foldReceived` puts the
 * plainly received files behind one line, because the desk's inventory lists them anyway, and
 * keeps every file with a problem or a note in view.
 */
export default function BulkUpload({
  upload,
  onUploaded,
  disabled = false,
  intro,
  camera = false,
  compact = false,
  foldReceived = false,
}) {
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(null)
  const [toast, setToast] = useState(null) // errors also pop up at the top right of the screen
  const [error, setError] = useState(null)
  const [over, setOver] = useState(false)
  const files = useRef(null)
  const folder = useRef(null)
  const photo = useRef(null)
  const zone = useRef(null)

  async function send(list) {
    if (!list.length || disabled) return
    setBusy(true)
    setError(null)
    setToast(null)
    setResults([])
    setSending({
      count: list.length,
      bytes: list.reduce((n, f) => n + f.size, 0),
      zip: list.length === 1 && /\.zip$/i.test(list[0].name),
    })
    // the box can sit below the fold on a desk page: bring the progress into view
    setTimeout(() => zone.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' }), 50)
    const form = new FormData()
    // a folder sends each file's path inside it, which the server only uses as a label
    list.forEach((f) => form.append('files', f, f.webkitRelativePath || f.name))
    try {
      const out = await upload(form)
      setResults(out)
      const bad = out.filter((r) => r.status === 'rejected')
      if (bad.length)
        setToast({
          id: Date.now(),
          title:
            bad.length === 1 ? '1 file was not accepted' : `${bad.length} files were not accepted`,
          lines: bad.slice(0, 3).map((r) => `${r.name}: ${r.message || LABEL.rejected}`),
          more: bad.length - 3,
        })
      onUploaded?.(out)
    } catch (e) {
      setError(e.message)
      setToast({ id: Date.now(), title: 'The upload did not work', lines: [e.message] })
    } finally {
      setBusy(false)
      setSending(null)
      if (files.current) files.current.value = ''
      if (folder.current) folder.current.value = ''
      if (photo.current) photo.current.value = ''
    }
  }

  return (
    <div className="bulk">
      <div
        ref={zone}
        className={`dropzone${compact ? ' dropzone-compact' : ''}${over ? ' over' : ''}${disabled ? ' off' : ''}`}
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
        {sending && <Working sending={sending} />}
        {!busy && <p>{intro || 'Drop a zip or your files here, or choose them below.'}</p>}
        {!busy && (
          <div className="bulk-buttons">
            <label className={`btn${busy || disabled ? ' disabled' : ''}`} htmlFor="bulk-files">
              Choose files or a zip
            </label>
            {camera && (
              <label
                className={`btn bulk-camera${busy || disabled ? ' disabled' : ''}`}
                htmlFor="bulk-photo"
              >
                Take a photo
              </label>
            )}
            <label
              className={`btn bulk-folder${busy || disabled ? ' disabled' : ''}`}
              htmlFor="bulk-folder"
            >
              Choose a folder
            </label>
          </div>
        )}
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
        {camera && (
          <input
            id="bulk-photo"
            ref={photo}
            type="file"
            className="sr-only"
            accept="image/*"
            capture="environment"
            disabled={busy || disabled}
            onChange={(e) => send([...e.target.files])}
          />
        )}
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
        {!busy && (
          <p className="small muted">
            PDF, JPG, PNG or a zip of them. Each file up to 10 MB. Password-protected PDFs and very
            blurry photos are not accepted.
          </p>
        )}
      </div>
      {toast && (
        <Toast
          key={toast.id}
          title={toast.title}
          lines={
            toast.more > 0
              ? [...toast.lines, `and ${toast.more} more, see the list below`]
              : toast.lines
          }
          onClose={() => setToast(null)}
        />
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {results.length > 0 && (
        <div aria-live="polite" data-testid="bulk-results">
          {foldReceived && results.some((r) => r.status === 'accepted') ? (
            // one line that opens the received list; files with a problem or a note stay in view
            <details className="ur-fold">
              <summary>
                <strong>{summarise(results)}</strong>{' '}
                <span className="ur-fold-hint">· show each file</span>
              </summary>
              <ResultRows rows={results.filter((r) => r.status === 'accepted')} />
            </details>
          ) : (
            <p className="bulk-summary">
              <strong>{summarise(results)}</strong>
            </p>
          )}
          {foldReceived ? (
            results.some((r) => r.status !== 'accepted') && (
              <ResultRows rows={results.filter((r) => r.status !== 'accepted')} />
            )
          ) : (
            <ResultRows rows={results} />
          )}
        </div>
      )}
    </div>
  )
}
