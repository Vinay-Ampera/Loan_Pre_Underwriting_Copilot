import { useState } from 'react'
import { api } from '../api/client'
import ClauseDiff from './ClauseDiff'
import PolicyReader from './PolicyReader'
import ReasonDialog from './ReasonDialog'
import StatusChip from './StatusChip'
import { day, originLabel, versionTone, when } from '../lib/policy'
import './PolicyHistory.css'

/**
 * Every version of one policy. Published versions are never edited or deleted: an older one can
 * be read, compared, restored into a draft (published like any change) or retired.
 */
export default function PolicyHistory({ detail, onChanged }) {
  const [open, setOpen] = useState(null) // { kind: 'read'|'compare', id, data }
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [dialogError, setDialogError] = useState(null)
  const active = detail.active
  const hasDraft = Boolean(detail.draft)

  async function show(kind, v) {
    setMsg(null)
    if (open?.id === v.id && open.kind === kind) return setOpen(null)
    try {
      const data =
        kind === 'read'
          ? await api.get(`/knowledge/versions/${v.id}`)
          : await api.get(`/knowledge/compare?a=${v.id}&b=${active.id}`)
      setOpen({ kind, id: v.id, data })
    } catch (e) {
      setMsg(e.message)
    }
  }
  async function restore(v) {
    setBusy(true)
    setMsg(null)
    try {
      await api.post(`/knowledge/versions/${v.id}/restore`)
      onChanged('change')
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function retire(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      await api.post(`/knowledge/versions/${dialog.id}/retire`, { reason, second_click: true })
      setDialog(null)
      onChanged()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="policy-history">
      <p className="muted">
        Old reports keep the clause text they cited. Restoring copies an older text into a new draft
        with a new version label; retiring takes a scheduled or replaced version out for good.
      </p>
      {msg && (
        <p className="field-error" role="alert">
          {msg}
        </p>
      )}
      <ul className="ph-list">
        {detail.versions.map((v) => {
          const [tone, label] = versionTone(v.status)
          return (
            <li key={v.id} className="ph-item card">
              <div className="ph-row">
                <div>
                  <strong className="mono">{v.version}</strong>{' '}
                  <StatusChip tone={tone}>{label}</StatusChip>
                  <p className="small muted">
                    Effective {day(v.effective_from)} · {v.clauses} clauses ·{' '}
                    {originLabel(v.origin)}
                    {v.published_by ? ` · ${v.published_by}` : ''}
                    {v.published_at ? `, ${when(v.published_at)}` : ''}
                  </p>
                  {v.reason && <p className="small">&ldquo;{v.reason}&rdquo;</p>}
                  {v.retired_reason && (
                    <p className="small muted">
                      Retired by {v.retired_by}: &ldquo;{v.retired_reason}&rdquo;
                    </p>
                  )}
                </div>
                <div className="ph-actions">
                  <button type="button" className="btn btn-ghost" onClick={() => show('read', v)}>
                    {open?.id === v.id && open.kind === 'read' ? 'Close' : 'Read'}
                  </button>
                  {active && v.id !== active.id && (
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => show('compare', v)}
                    >
                      Compare with the version in force
                    </button>
                  )}
                  {v.status !== 'active' && (
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={busy || hasDraft}
                      title={hasDraft ? 'Discard the current draft first.' : undefined}
                      onClick={() => restore(v)}
                    >
                      Restore as a draft
                    </button>
                  )}
                  {(v.status === 'scheduled' || v.status === 'superseded') && (
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={busy}
                      onClick={() => setDialog(v)}
                    >
                      Retire…
                    </button>
                  )}
                </div>
              </div>
              {open?.id === v.id && open.kind === 'read' && (
                <PolicyReader version={open.data} admin />
              )}
              {open?.id === v.id && open.kind === 'compare' && (
                <ClauseDiff
                  changes={open.data}
                  title={`From ${v.version} to the version in force`}
                />
              )}
            </li>
          )
        })}
      </ul>
      {dialog && (
        <ReasonDialog
          title={`Retire version ${dialog.version}?`}
          confirmLabel="Yes, retire"
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={retire}
        >
          <p>
            {dialog.status === 'scheduled'
              ? 'It will not take effect. Its text can still be restored into a draft later.'
              : 'It stays readable for old reports but can no longer be put back as it is.'}
          </p>
        </ReasonDialog>
      )}
    </div>
  )
}
