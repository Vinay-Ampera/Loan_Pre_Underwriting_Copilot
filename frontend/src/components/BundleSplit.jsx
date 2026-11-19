import { useState } from 'react'
import { api } from '../api/client'
import { docLabel } from '../lib/docLabels'
import ConfirmDialog from './ConfirmDialog'
import StatusChip from './StatusChip'
import './BundleSplit.css'

const strip = (segments) =>
  segments.map(({ page_from, page_to, doc_type }) => ({ page_from, page_to, doc_type }))
const sameSplit = (a, b) =>
  a.length === b.length &&
  a.every(
    (s, i) =>
      s.page_from === b[i].page_from && s.page_to === b[i].page_to && s.doc_type === b[i].doc_type,
  )

/** One row per page: where a document starts, what it is, and which document a page continues. */
export function pageRows(segments, pages) {
  return Array.from({ length: pages }, (_, i) => {
    const page = i + 1
    const seg = segments.find((s) => page >= s.page_from && page <= s.page_to)
    return {
      page,
      start: seg?.page_from === page,
      type: seg?.doc_type ?? 'unknown',
      from: seg?.page_from ?? page,
    }
  })
}

/** A new document starts on this page. It is "not recognised" until the officer says what it is. */
export function startAt(segments, page) {
  return segments.flatMap((s) =>
    page > s.page_from && page <= s.page_to
      ? [
          { ...s, page_to: page - 1 },
          { page_from: page, page_to: s.page_to, doc_type: 'unknown' },
        ]
      : [s],
  )
}

/** The document that starts on this page joins the one before it. */
export function joinBack(segments, page) {
  const out = []
  for (const s of segments) {
    if (s.page_from === page && out.length)
      out[out.length - 1] = { ...out[out.length - 1], page_to: s.page_to }
    else out.push(s)
  }
  return out
}

/**
 * One PDF that holds several documents (Stage 10, Part D). The server proposes where each document
 * starts from the title on each page; the officer ticks the pages where a new document starts and
 * says what each one is. Every change is saved at once (nothing is cut yet, so nothing to
 * confirm). Only "Confirm the split" cuts the PDF, and it asks for the second click. The original
 * PDF is never changed.
 */
export default function BundleSplit({ caseId, bundle, docTypes, editable, onChange, onError }) {
  const [saving, setSaving] = useState(false)
  const [dialog, setDialog] = useState(null) // 'cut' | 'remove'
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState(null)
  const segments = bundle.segments
  const proposed = bundle.proposed?.length ? bundle.proposed : segments
  const rows = pageRows(segments, bundle.pages)
  const types = [...new Set([...docTypes, 'unknown', ...segments.map((s) => s.doc_type)])]
  const base = `/cases/${caseId}/documents/${bundle.id}`

  async function save(next) {
    setSaving(true)
    try {
      onChange(await api.put(`${base}/split`, { segments: strip(next) }))
    } catch (e) {
      onError?.(e.message)
    } finally {
      setSaving(false)
    }
  }
  const toggle = (page, on) => save(on ? startAt(segments, page) : joinBack(segments, page))
  const relabel = (page, doc_type) =>
    save(segments.map((s) => (s.page_from === page ? { ...s, doc_type } : s)))

  async function openPdf() {
    try {
      const blob = await api.blob(`${base}/file`)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (e) {
      onError?.(e.message)
    }
  }
  async function cut() {
    setBusy(true)
    setDialogError(null)
    try {
      const res = await api.post(`${base}/split/confirm`, { second_click: true })
      setDialog(null)
      onChange(res.inventory, res.results)
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    setBusy(true)
    setDialogError(null)
    try {
      await api.del(base)
      setDialog(null)
      onChange(await api.get(`/cases/${caseId}/inventory`))
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card inv-card bundle" aria-label={`Split ${bundle.name}`}>
      <header className="bundle-head">
        <div>
          <h3>
            <span className="mono">{bundle.name}</span>{' '}
            <StatusChip tone="refer">Several documents</StatusChip>
          </h3>
          <p className="muted">
            This PDF has {bundle.pages} pages and looks like {segments.length} documents. Each page
            was read for its title; a page without one continues the document before it. Tick the
            pages where a new document starts and say what each one is. The original PDF is kept as
            it is.
          </p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={openPdf}>
          Open the PDF
        </button>
      </header>

      <ol className="bundle-list">
        {rows.map((r) => (
          <li key={r.page} className={`bundle-row${r.start ? ' starts' : ''}`}>
            <label className="bundle-tick">
              <input
                type="checkbox"
                aria-label={`A new document starts on page ${r.page}`}
                checked={r.start}
                disabled={!editable || saving || r.page === 1}
                onChange={(e) => toggle(r.page, e.target.checked)}
              />
              <span className="bundle-page">Page {r.page}</span>
            </label>
            {r.start ? (
              <select
                className="select"
                aria-label={`What the document starting on page ${r.page} is`}
                value={r.type}
                disabled={!editable || saving}
                onChange={(e) => relabel(r.page, e.target.value)}
              >
                {types.map((t) => (
                  <option key={t} value={t}>
                    {docLabel(t)}
                  </option>
                ))}
              </select>
            ) : (
              <span className="small muted">continues the document from page {r.from}</span>
            )}
          </li>
        ))}
      </ol>

      {editable && (
        <div className="bundle-foot">
          <span className="bundle-foot-left">
            <button type="button" className="btn btn-ghost" onClick={() => setDialog('remove')}>
              Remove this PDF
            </button>
            {!sameSplit(segments, proposed) && (
              <button
                type="button"
                className="btn btn-ghost"
                disabled={saving}
                onClick={() => save(proposed)}
              >
                Back to the proposed split
              </button>
            )}
          </span>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving}
            onClick={() => setDialog('cut')}
          >
            Confirm the split
          </button>
        </div>
      )}

      {dialog === 'cut' && (
        <ConfirmDialog
          title="Cut this PDF into documents?"
          confirmLabel="Yes, split it"
          danger={false}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={cut}
        >
          <p>
            {segments.length === 1
              ? 'The whole PDF will be filed as one document.'
              : `${segments.length} documents will be cut from this PDF and filed to the right people.`}{' '}
            Each one is checked like a file of its own. The original PDF stays untouched in the
            case.
          </p>
        </ConfirmDialog>
      )}
      {dialog === 'remove' && (
        <ConfirmDialog
          title="Remove this PDF?"
          confirmLabel="Yes, remove it"
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={remove}
        >
          <p>
            <span className="mono">{bundle.name}</span> will be removed from the case and nothing
            will be cut from it. You can upload it again later.
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}
