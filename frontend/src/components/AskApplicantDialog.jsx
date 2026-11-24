import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { formatDay } from '../lib/format'
import ConfirmDialog from './ConfirmDialog'
import Dialog from './Dialog'
import SendLinkDialog from './SendLinkDialog'
import RequestedItems, { isComplete, toBody } from './RequestedItems'
import { SectionLoader } from './Loading'

/** The address the applicant opens: this site's own origin plus the link path (`/u#token`). */
export const linkUrl = (path) => `${window.location.origin}${path}`

/**
 * Which wording fits: the button always names what really happens. No link yet: it creates one.
 * An open link the applicant has not used to send: it only shows the address. An open link of an
 * applicant who already sent: it asks for more. An expired link: reopen it or make a new one. A
 * switched-off link cannot be reopened.
 */
export function modeOf(link) {
  if (!link) return 'create'
  if (link.state === 'active') return link.sent ? 'more' : 'share'
  return link.state === 'expired' ? 'expired' : 'disabled'
}

const COPY = {
  create: {
    title: 'Ask the applicant for the rest?',
    label: 'Create the link',
  },
  share: {
    title: "Share the applicant's link?",
    label: 'Show the link',
  },
  more: {
    title: 'Ask the applicant for more documents?',
    label: 'Ask for more',
  },
  disabled: {
    title: 'This link was switched off',
    label: 'Make a new link',
  },
}

function Body({ mode, link }) {
  if (mode === 'create')
    return (
      <p>
        This makes a secure upload link for this case. It stays open for a limited time, takes files
        only, and shows the applicant what is still needed. You will see the address once. Nothing
        is sent until you choose to send it.
      </p>
    )
  if (mode === 'share')
    return (
      <p>
        This case already has an open link, open until {formatDay(link.expires_at)}. Nothing new is
        made. You will see the address so you can copy it or send it as a message.
      </p>
    )
  if (mode === 'more')
    return (
      <p>
        The applicant&apos;s page will show what is in and what is still needed, and they can add
        files. Their link stays open until {formatDay(link.expires_at)} (it is extended if it is
        about to end). Nothing is sent to them until you send the link message.
      </p>
    )
  return (
    <p>
      A switched-off link cannot be opened again. Make a new link with a new address; the old one
      stays switched off.
    </p>
  )
}

function ManageLink({ link }) {
  if (!link?.case_no) return null
  return (
    <p className="small">
      <Link to={`/links?case=${encodeURIComponent(link.case_no)}`}>
        Manage this case&apos;s links on the Upload links page
      </Link>
    </p>
  )
}

/**
 * "Ask the applicant": a link for this case that takes files only. It is an outward action, so it
 * needs the second click. The address is shown once (only its hash is kept), with a copy button
 * and a way to send it as the Stage 9 "Upload link" message.
 */
export default function AskApplicantDialog({ caseId, recipient, docTypes = [], onClose, onDone }) {
  const info = useAsync(() => api.get(`/cases/${caseId}/link`), [caseId])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [made, setMade] = useState(null)
  const [copied, setCopied] = useState(false)
  const [sending, setSending] = useState(false)
  const [req, setReq] = useState({ items: [], note: '' })

  const link = info.data?.link ?? null
  const mode = modeOf(link)
  // after the applicant has sent, asking for more must say what is needed
  const needsRequest = Boolean(link?.sent) && mode !== 'share'
  const ready = !needsRequest || isComplete(req)
  const fields = needsRequest && (
    <RequestedItems docTypes={docTypes} value={req} onChange={setReq} />
  )

  async function ask(reopen = false) {
    setBusy(true)
    setError(null)
    try {
      const body = {
        second_click: true,
        ...(reopen ? { reopen: true } : {}),
        ...(needsRequest ? toBody(req) : {}),
      }
      setMade(await api.post(`/cases/${caseId}/ask-applicant`, body))
      onDone?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(linkUrl(made.path))
      setCopied(true)
    } catch {
      setError('Copying did not work. Select the address and copy it by hand.')
    }
  }

  if (!made && info.loading)
    return (
      <Dialog title="Ask the applicant" onClose={onClose} labelledBy="ask-link-title">
        <SectionLoader label="Loading the upload link" />
      </Dialog>
    )
  if (!made && mode === 'expired')
    return (
      <Dialog
        title="The applicant's link has expired"
        onClose={onClose}
        labelledBy="ask-link-title"
      >
        <p>
          The link for <span className="mono">{link.case_no}</span> expired on{' '}
          {formatDay(link.expires_at)}, so the applicant can no longer use it. Reopen it and the
          address they already have works again, for the standard period. Or make a new link with a
          new address.
        </p>
        <ManageLink link={link} />
        {fields}
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose} data-autofocus>
            Cancel
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || !ready}
            onClick={() => ask(false)}
          >
            Make a new link
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !ready}
            onClick={() => ask(true)}
          >
            Reopen this link
          </button>
        </div>
      </Dialog>
    )
  if (!made)
    return (
      <ConfirmDialog
        title={COPY[mode].title}
        confirmLabel={COPY[mode].label}
        danger={false}
        busy={busy || !ready}
        error={error}
        onClose={onClose}
        onConfirm={() => ask(false)}
      >
        <Body mode={mode} link={link} />
        {mode === 'disabled' && <ManageLink link={link} />}
        {fields}
      </ConfirmDialog>
    )
  if (sending) {
    return (
      <SendLinkDialog
        caseId={caseId}
        linkId={made.link_id}
        token={new URL(linkUrl(made.path)).hash.slice(1)}
        recipient={recipient}
        onClose={onClose}
      />
    )
  }
  // the applicant already has this address: the page now shows the request, so say that first
  if (needsRequest && made.new_link === false)
    return (
      <Dialog title="Your request is saved" onClose={onClose} labelledBy="ask-link-title">
        <p>
          The applicant&apos;s page now shows what you asked for. Tell them to open the link they
          already have.
        </p>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          {made.token && (
            <>
              <button type="button" className="btn" onClick={copy}>
                {copied ? 'Copied' : 'Copy the link'}
              </button>
              <button type="button" className="btn" onClick={() => setSending(true)}>
                Send it as a message
              </button>
            </>
          )}
          <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
            Done
          </button>
        </div>
      </Dialog>
    )
  return (
    <Dialog title="The applicant's link" onClose={onClose} labelledBy="ask-link-title">
      {made.token ? (
        <>
          <p>Copy this address. You can copy it again later from the Upload links page.</p>
          <input
            className="input mono"
            readOnly
            aria-label="Upload link address"
            value={linkUrl(made.path)}
            onFocus={(e) => e.target.select()}
          />
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={copy} data-autofocus>
              {copied ? 'Copied' : 'Copy the link'}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setSending(true)}>
              Send it as a message
            </button>
            <button type="button" className="btn" onClick={onClose}>
              Done
            </button>
          </div>
        </>
      ) : (
        <>
          <p>
            The applicant&apos;s link for this case is still open, and it has been extended. Its
            address cannot be shown here. Open the Upload links page to copy it or to make a new
            address.
          </p>
          <div className="dialog-actions">
            <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
              Close
            </button>
          </div>
        </>
      )}
    </Dialog>
  )
}
