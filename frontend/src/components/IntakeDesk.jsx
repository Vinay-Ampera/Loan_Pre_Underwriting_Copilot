import { useState } from 'react'
import { api } from '../api/client'
import { downloadFile } from '../lib/download'
import AskApplicantDialog from './AskApplicantDialog'
import BulkUpload, { summarise } from './BulkUpload'
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
  children, // more ways to add a file (the officer's "label it yourself"), shown under the box
}) {
  const [ask, setAsk] = useState(false)
  const [proceed, setProceed] = useState(false)
  const [unsent, setUnsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [splitNote, setSplitNote] = useState(null)

  const c = inventory.counts
  const toSplit = inventory.bundles?.length ?? 0
  const nothingYet = c.received + c.unassigned + c.unrecognised + toSplit === 0
  const missingNow = c.missing > 0 || inventory.depends_on_employment.length > 0
  const blocked = inventory.essential_missing > 0
  const waiting = Boolean(inventory.waiting_for_applicant)
  // after the officer asked for more, the applicant had already sent once: say what is awaited
  const unsentNote = inventory.asked_for_more
    ? 'You asked the applicant for more files and they have not sent them yet'
    : 'The applicant has not pressed Send to the bank yet'
  const ready = !blocked && toSplit === 0 && (!missingNow || inventory.proceeded)

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
      const next = await api.post(`/cases/${caseId}/intake/proceed`, { second_click: true })
      setInventory(next)
      setProceed(false)
      if (next.waiting_for_applicant) setUnsent(true)
      else onContinue?.()
    } catch (e) {
      setError(e.message)
      setProceed(false)
    } finally {
      setBusy(false)
    }
  }
  async function goOnUnsent() {
    setBusy(true)
    setError(null)
    try {
      setInventory(
        await api.post(`/cases/${caseId}/intake/continue-unsent`, { second_click: true }),
      )
      setUnsent(false)
      onContinue?.()
    } catch (e) {
      setError(e.message)
      setUnsent(false)
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
          compact={!nothingYet}
          foldReceived
          intro={
            nothingYet
              ? 'Drop a zip, a folder or all the files here. They are filed to a person and checked once.'
              : 'Add more: drop a zip, a folder or files here.'
          }
        />
      )}
      {children}
      {!nothingYet && (
        <Inventory
          caseId={caseId}
          onSplit={(results) => setSplitNote(resultsOf({ results }))}
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
      {splitNote && (
        <p className="small" role="status">
          Split done: <strong>{summarise(splitNote)}</strong>
        </p>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {/* the next step, kept in view at the bottom of the window while the list is long: why a
          button is not available yet, then the buttons */}
      {(!nothingYet || onContinue) && (
        <div className="desk-next">
          {editable && waiting && !nothingYet && (
            <p className="small muted" role="status">
              {unsentNote}, so more files may still arrive.
            </p>
          )}
          {toSplit > 0 && (
            <p className="small muted">
              A PDF with several documents is waiting for you to confirm how it is split.
            </p>
          )}
          {blocked && !nothingYet && (
            <p className="small muted">
              The PAN card, the Aadhaar card and the photograph are needed for every person before
              the case can be submitted.
            </p>
          )}
          {onContinue && nothingYet && (
            <p className="small muted">Add the applicant&apos;s documents above first.</p>
          )}
          {/* why "Continue" is off when only missing papers or the employment type hold it */}
          {onContinue &&
            !nothingYet &&
            !blocked &&
            toSplit === 0 &&
            missingNow &&
            !inventory.proceeded && (
              <>
                {inventory.depends_on_employment.length > 0 && (
                  <p className="small muted">
                    State the employment type above: the income papers needed depend on it.
                  </p>
                )}
                {c.missing > 0 && (
                  <p className="small muted">
                    Some documents are still missing: ask the applicant for them, or proceed anyway.
                  </p>
                )}
              </>
            )}
          <div className="desk-actions">
            {!nothingYet && (
              <button type="button" className="btn btn-ghost desk-zip" onClick={zip}>
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
                  disabled={blocked || toSplit > 0}
                  title={
                    blocked
                      ? 'The identity documents are needed first.'
                      : toSplit > 0
                        ? 'Split the PDF first.'
                        : undefined
                  }
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
                onClick={waiting ? () => setUnsent(true) : onContinue}
              >
                Continue to the application form
              </button>
            )}
          </div>
        </div>
      )}

      {ask && (
        <AskApplicantDialog
          caseId={caseId}
          recipient={recipient}
          docTypes={docTypes}
          onClose={() => setAsk(false)}
          onDone={onChanged}
        />
      )}
      {unsent && (
        <ConfirmDialog
          title="Continue before the applicant has sent?"
          confirmLabel="Yes, continue anyway"
          danger={false}
          busy={busy}
          onClose={() => setUnsent(false)}
          onConfirm={goOnUnsent}
        >
          <p>
            {unsentNote}, so more files may still arrive. If you continue now, the case is checked
            with the files received so far. The link stays open until you submit.
          </p>
        </ConfirmDialog>
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
