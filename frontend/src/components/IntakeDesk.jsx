import { useState } from 'react'
import { api } from '../api/client'
import { downloadFile } from '../lib/download'
import AskApplicantDialog from './AskApplicantDialog'
import BulkUpload from './BulkUpload'
import ConfirmDialog from './ConfirmDialog'
import Inventory from './Inventory'
import './IntakeDesk.css'

/** Normalise the officer upload response to what BulkUpload shows. */
export const resultsOf = (res) =>
  res.results.map((r) => ({ name: r.name, status: r.status, message: r.message }))

/**
 * The intake desk: add a zip, a folder or files, read the inventory, correct a type or person,
 * then either ask the applicant for the rest, go on anyway (second click) or continue to the
 * form. Nothing here changes a score; it only files the documents.
 */
export default function IntakeDesk({
  caseId,
  inventory,
  setInventory,
  docTypes,
  editable,
  recipient,
  onContinue,
  onChanged,
}) {
  const [ask, setAsk] = useState(false)
  const [proceed, setProceed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const c = inventory.counts
  const nothingYet = c.received + c.unassigned + c.unrecognised === 0
  const missingNow = c.missing > 0 || inventory.depends_on_employment.length > 0
  const blocked = inventory.essential_missing > 0
  const ready = !blocked && (!missingNow || inventory.proceeded)

  async function upload(form) {
    const res = await api.upload(`/cases/${caseId}/intake/files`, form)
    setInventory(res.inventory)
    onChanged?.()
    return resultsOf(res)
  }
  async function goOn() {
    setBusy(true)
    setError(null)
    try {
      setInventory(await api.post(`/cases/${caseId}/intake/proceed`, { second_click: true }))
      setProceed(false)
      onContinue?.()
    } catch (e) {
      setError(e.message)
      setProceed(false)
    } finally {
      setBusy(false)
    }
  }
  async function zip() {
    try {
      await downloadFile(`/cases/${caseId}/files.zip`, `${caseId}-files.zip`)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="desk">
      {editable && (
        <BulkUpload
          upload={upload}
          intro="Drop a zip, a folder or all the files here. They are filed to a person and checked once."
        />
      )}
      {!nothingYet && (
        <Inventory
          caseId={caseId}
          inventory={inventory}
          docTypes={docTypes}
          editable={editable}
          onChange={(inv) => {
            setInventory(inv)
            onChanged?.()
          }}
          onError={setError}
        />
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="desk-actions">
        {!nothingYet && (
          <button type="button" className="btn btn-ghost" onClick={zip}>
            Download all files (zip)
          </button>
        )}
        {editable && !nothingYet && missingNow && (
          <>
            <button type="button" className="btn" onClick={() => setAsk(true)}>
              Ask the applicant
            </button>
            <button
              type="button"
              className="btn"
              disabled={blocked}
              title={blocked ? 'The identity documents are needed first.' : undefined}
              onClick={() => setProceed(true)}
            >
              Proceed anyway
            </button>
          </>
        )}
        {editable && !nothingYet && !missingNow && (
          <button type="button" className="btn" onClick={() => setAsk(true)}>
            Ask the applicant for more
          </button>
        )}
        {onContinue && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={!ready || nothingYet}
            onClick={onContinue}
          >
            Continue to the application form
          </button>
        )}
      </div>
      {blocked && !nothingYet && (
        <p className="small muted">
          The PAN card, the Aadhaar card and the photograph are needed for every person before the
          case can be submitted.
        </p>
      )}

      {ask && (
        <AskApplicantDialog
          caseId={caseId}
          recipient={recipient}
          onClose={() => setAsk(false)}
          onDone={onChanged}
        />
      )}
      {proceed && (
        <ConfirmDialog
          title="Go on with documents missing?"
          confirmLabel="Yes, proceed anyway"
          danger={false}
          busy={busy}
          onClose={() => setProceed(false)}
          onConfirm={goOn}
        >
          <p>
            The assessment will stop with a request for the missing documents if they are required
            for this loan. You can still add them before you submit.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
