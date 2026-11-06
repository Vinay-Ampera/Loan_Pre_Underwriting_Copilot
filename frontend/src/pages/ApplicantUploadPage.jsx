import { useCallback, useEffect, useState } from 'react'
import { publicApi, tokenFromHash } from '../api/public'
import BrandMark from '../components/BrandMark'
import BulkUpload from '../components/BulkUpload'
import ConfirmDialog from '../components/ConfirmDialog'
import { LOAN_TYPES, loanLabel } from '../components/LoanTypePicker'
import { docLabel } from '../lib/docLabels'
import './ApplicantUploadPage.css'

const FRAUD =
  'Pramaan staff will never ask you for your OTP, PIN or password, by phone, email or message. If anyone does, do not share it.'
const MAP = { received: 'accepted', 'already received': 'ignored', 'not accepted': 'rejected' }

/** What is still to send, as counts only. Never a file name, a status or an outcome. */
function Checklist({ checklist }) {
  if (!checklist) return null
  return (
    <section className="card ap-card" aria-label="What to send">
      <h2>What to send</h2>
      {checklist.people.map((p) => (
        <div key={p.who}>
          {checklist.people.length > 1 && <h3 className="ap-who">{p.who}</h3>}
          <ul className="ap-list">
            {p.items.map((i) => (
              <li key={i.type} className={i.have >= i.needed ? 'met' : 'missing'}>
                <span aria-hidden="true">{i.have >= i.needed ? '✓' : '!'}</span>
                <span>
                  {docLabel(i.type)}
                  {i.needed > 1 && (
                    <span className="muted">
                      {' '}
                      ({i.have} of {i.needed})
                    </span>
                  )}
                </span>
                <span className="sr-only">{i.have >= i.needed ? 'received' : 'still needed'}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {checklist.after_employment.length > 0 && (
        <p className="small muted">
          Other items depend on whether you are salaried or self-employed. Send your request first
          and they will be listed here.
        </p>
      )}
    </section>
  )
}

/**
 * What this applicant sent through this link, with a way to look at each file and to take it
 * back. It shows the file's name and a plain result, nothing the bank read from it. Taking a file
 * back needs the second click and is possible only until Send to the bank.
 */
function MyFiles({ token, refreshKey, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [toRemove, setToRemove] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
    publicApi
      .myFiles(token)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [token, refreshKey])

  async function view(f) {
    setError(null)
    const tab = window.open('', '_blank') // opened now, so a phone does not block it
    try {
      const url = URL.createObjectURL(await publicApi.fileBlob(token, f.id))
      if (tab) tab.location.href = url
      else window.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000)
    } catch (e) {
      tab?.close()
      setError(e.message)
    }
  }
  async function remove() {
    setBusy(true)
    try {
      const out = await publicApi.removeFile(token, toRemove.id)
      setData((d) => ({ ...d, files: d.files.filter((x) => x.id !== toRemove.id) }))
      onChanged(out.checklist)
      setToRemove(null)
    } catch (e) {
      setError(e.message)
      setToRemove(null)
    } finally {
      setBusy(false)
    }
  }

  if (!data || data.files.length === 0) return null
  return (
    <section className="card ap-card" aria-label="Your files">
      <h2>Your files</h2>
      <ul className="ap-files">
        {data.files.map((f) => (
          <li key={f.id}>
            <div className="ap-file-name">
              <strong>{f.name}</strong>
              <span className="small muted">{f.result}</span>
            </div>
            <div className="ap-file-actions">
              {f.can_view && (
                <button type="button" className="btn" onClick={() => view(f)}>
                  View<span className="sr-only"> {f.name}</span>
                </button>
              )}
              {data.can_remove && (
                <button type="button" className="btn btn-ghost" onClick={() => setToRemove(f)}>
                  Remove<span className="sr-only"> {f.name}</span>
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {!data.can_remove && (
        <p className="small muted">
          Files can no longer be removed here. Please contact your loan officer if one is wrong.
        </p>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {toRemove && (
        <ConfirmDialog
          title="Remove this file?"
          confirmLabel="Yes, remove it"
          busy={busy}
          onClose={() => setToRemove(null)}
          onConfirm={remove}
        >
          <p>
            <strong>{toRemove.name}</strong> will be deleted. You can send a different one after.
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}

function RequestForm({ view, onSent, token }) {
  const [f, setF] = useState({
    loan_type: view.loan_type || '',
    loan_amount: '',
    tenure_months: '',
    purpose: '',
    employment_type: 'salaried',
    declared_monthly_income: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }))
  const education = (view.loan_type || f.loan_type) === 'education'

  async function submit(e) {
    e.preventDefault()
    setError(null)
    if (!f.loan_type) return setError('Choose the kind of loan.')
    if (!(Number(f.loan_amount) > 0)) return setError('Enter the amount you would like.')
    if (!(Number(f.tenure_months) > 0)) return setError('Enter the number of months.')
    setBusy(true)
    try {
      await publicApi.request(token, {
        loan_type: f.loan_type,
        loan_amount: Number(f.loan_amount),
        tenure_months: Number(f.tenure_months),
        purpose: f.purpose.trim() || null,
        employment_type: f.employment_type,
        declared_monthly_income:
          f.declared_monthly_income === '' ? null : Number(f.declared_monthly_income),
      })
      onSent()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card ap-card" onSubmit={submit} noValidate>
      <h2>1. Your request</h2>
      <p className="muted">
        This is your own statement. The bank will check it against your documents.
      </p>
      <div className="ap-grid">
        {!view.loan_type && (
          <div className="field">
            <label htmlFor="ap-loan">Kind of loan</label>
            <select id="ap-loan" className="select" value={f.loan_type} onChange={set('loan_type')}>
              <option value="">Choose…</option>
              {LOAN_TYPES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="ap-amount">Amount you would like (INR)</label>
          <input
            id="ap-amount"
            className="input"
            type="number"
            min="0"
            value={f.loan_amount}
            onChange={set('loan_amount')}
          />
        </div>
        <div className="field">
          <label htmlFor="ap-tenure">For how many months</label>
          <input
            id="ap-tenure"
            className="input"
            type="number"
            min="1"
            value={f.tenure_months}
            onChange={set('tenure_months')}
          />
        </div>
        <div className="field">
          <label htmlFor="ap-purpose">
            What it is for <span className="opt">(optional)</span>
          </label>
          <input id="ap-purpose" className="input" value={f.purpose} onChange={set('purpose')} />
        </div>
        <div className="field">
          <label htmlFor="ap-emp">{education ? 'Co-applicant works as' : 'You work as'}</label>
          <select
            id="ap-emp"
            className="select"
            value={f.employment_type}
            onChange={set('employment_type')}
          >
            <option value="salaried">Salaried</option>
            <option value="self_employed">Self-employed</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="ap-income">
            {education ? 'Co-applicant' : 'Your'} monthly income (INR){' '}
            <span className="opt">(optional)</span>
          </label>
          <input
            id="ap-income"
            className="input"
            type="number"
            min="0"
            value={f.declared_monthly_income}
            onChange={set('declared_monthly_income')}
          />
        </div>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="ap-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy
            ? 'Saving…'
            : view.request_received
              ? 'Send the corrected request'
              : 'Save my request'}
        </button>
      </div>
    </form>
  )
}

/**
 * The applicant's page. No account, no sign-in. It can take a request and files and show what is
 * still needed; it can never show a file, a score, a status or an outcome. The link's token is
 * read from the address fragment, which the browser never sends to a server.
 */
export default function ApplicantUploadPage() {
  const [token] = useState(() => tokenFromHash(window.location.hash))
  const [view, setView] = useState(null)
  const [dead, setDead] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const [done, setDone] = useState(null)
  const [reopen, setReopen] = useState(false)
  const [filesKey, setFilesKey] = useState(0)

  const load = useCallback(async () => {
    try {
      setView(await publicApi.link(token))
    } catch (e) {
      if (e.status === 404 || e.status === 0 || e.status === 429) setDead(e.status !== 429)
      if (e.status === 429) setError(e.message)
    }
  }, [token])
  useEffect(() => {
    load()
  }, [load])

  async function upload(form) {
    const res = await publicApi.files(token, form)
    setView((v) => ({ ...v, checklist: res.checklist, accepting_files: true }))
    setFilesKey((k) => k + 1)
    return res.files.map((f) => ({
      name: f.name,
      status: MAP[f.result] || 'accepted',
      message: f.reason,
    }))
  }
  async function send() {
    setBusy(true)
    setError(null)
    try {
      setDone(await publicApi.send(token))
      setConfirm(false)
    } catch (e) {
      setError(e.message)
      setConfirm(false)
    } finally {
      setBusy(false)
    }
  }

  const shell = (children) => (
    <div className="ap-page">
      <header className="ap-top">
        <BrandMark />
      </header>
      <main className="ap-main">{children}</main>
      <footer className="ap-foot small muted">{FRAUD}</footer>
    </div>
  )

  if (dead || !token)
    return shell(
      <section className="card ap-card" role="alert">
        <h1>This link is not active</h1>
        <p>
          The link may have expired or been switched off. Please contact your loan officer for a new
          one.
        </p>
      </section>,
    )
  if (!view)
    return shell(
      <p className="muted" aria-busy="true">
        Opening…
      </p>,
    )
  if (done)
    return shell(
      <section className="card ap-card" aria-live="polite">
        <h1>Thank you. We have it.</h1>
        <p>
          Your reference is <strong className="mono">{done.reference}</strong>. Keep it in case you
          speak to your loan officer.
        </p>
        {done.incomplete && (
          <p className="muted">
            Some items were not sent yet. You can open this same link again to add them while it is
            open.
          </p>
        )}
        <p className="muted">The bank will contact you if it needs anything else.</p>
      </section>,
    )

  const showRequest = view.request_open && (!view.request_received || reopen)
  const canFiles = view.request_received || view.checklist
  const missing = view.checklist && !view.checklist.complete

  return shell(
    <>
      <h1>
        Send your documents
        {view.loan_type && <span className="muted"> · {loanLabel(view.loan_type)}</span>}
      </h1>
      <p className="muted">This link is open until {view.expires_on}.</p>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}

      {showRequest ? (
        <RequestForm
          view={view}
          token={token}
          onSent={() => {
            setReopen(false)
            load()
          }}
        />
      ) : (
        view.request_open && (
          <section className="card ap-card">
            <h2>1. Your request</h2>
            <p>Your request was received.</p>
            <div className="ap-actions">
              <button type="button" className="btn" onClick={() => setReopen(true)}>
                Change my request
              </button>
            </div>
          </section>
        )
      )}

      {canFiles && (
        <>
          <Checklist checklist={view.checklist} />
          <section className="card ap-card">
            <h2>{view.request_open ? '2. Your documents' : 'Your documents'}</h2>
            {view.accepting_files ? (
              <BulkUpload
                upload={upload}
                camera
                intro="Drop a zip or your files here. Photos and scans must be sharp and show the whole page."
              />
            ) : (
              <p role="status">This link is not accepting files right now.</p>
            )}
          </section>
          <MyFiles
            token={token}
            refreshKey={filesKey}
            onChanged={(checklist) => setView((v) => ({ ...v, checklist }))}
          />
          {view.accepting_files && (
            <section className="card ap-card ap-send">
              <h2>{view.request_open ? '3. Send to the bank' : 'Send to the bank'}</h2>
              {missing && (
                <p className="ap-warn" role="status">
                  Some items on the list are not in yet. You can send what you have now and add the
                  rest later with this same link.
                </p>
              )}
              <div className="ap-actions">
                <button type="button" className="btn btn-primary" onClick={() => setConfirm(true)}>
                  Send to the bank
                </button>
              </div>
            </section>
          )}
        </>
      )}

      {confirm && (
        <ConfirmDialog
          title="Send to the bank?"
          confirmLabel="Yes, send"
          danger={false}
          busy={busy}
          onClose={() => setConfirm(false)}
          onConfirm={send}
        >
          <p>
            {missing
              ? 'Some items are still missing. The bank will see that your submission is incomplete.'
              : 'Everything on the list is in.'}{' '}
            Sending lets the loan officer start. You will get a reference number.
          </p>
        </ConfirmDialog>
      )}
    </>,
  )
}
