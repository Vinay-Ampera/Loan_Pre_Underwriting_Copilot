import { useState } from 'react'
import { downloadFile } from '../lib/download'

// the day in the file name is the person's own
const today = () => new Date().toLocaleDateString('en-CA')

/** Download a case list as CSV (Stage 12 Part C). No dialog: a download changes nothing. */
export default function ExportButton({ path, children }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  async function save() {
    setBusy(true)
    setError(null)
    try {
      await downloadFile(path, `pramaan-cases-${today()}.csv`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button type="button" className="btn" onClick={save} disabled={busy}>
        {children}
      </button>
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </>
  )
}
