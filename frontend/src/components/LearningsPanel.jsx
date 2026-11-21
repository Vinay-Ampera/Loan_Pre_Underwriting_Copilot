import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import ReasonDialog from './ReasonDialog'
import StatusChip from './StatusChip'
import { EmptyState, ErrorState, Skeleton } from './States'
import { loanLabel } from './LoanTypePicker'
import { day, when } from '../lib/policy'
import './LearningsPanel.css'

const FILTERS = [
  ['all', 'All'],
  ['approved', 'In use'],
  ['paused', 'Paused'],
  ['expired', 'Expired'],
  ['retired', 'Retired'],
]
const TONE = {
  approved: ['approve', 'In use'],
  paused: ['refer', 'Paused'],
  expired: ['neutral', 'Expired'],
  retired: ['stopped', 'Retired'],
}

/**
 * What the system has learned: approved precedents, how often each lifted a borderline case,
 * and the ones a policy change paused. The admin confirms a paused one again or retires it.
 */
export default function LearningsPanel() {
  const [filter, setFilter] = useState('all')
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/knowledge/learnings?status=${filter}`),
    [filter],
  )
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState(null)

  async function confirm(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      await api.post(`/knowledge/learnings/${dialog.item.id}/${dialog.kind}`, {
        reason,
        second_click: true,
      })
      setDialog(null)
      reload()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const c = data?.counts
  return (
    <div className="learnings">
      <p className="muted">
        A precedent helps only a borderline case of the same loan type, never over a hard rule, and
        only until it expires. Proposals waiting for you are in the{' '}
        <Link to="/admin/precedents">Precedents queue</Link>.
      </p>
      {c && (
        <ul className="lr-counts" aria-label="Counts">
          <li>
            <strong className="num">{c.approved}</strong> in use
          </li>
          <li>
            <strong className="num">{c.paused}</strong> paused
          </li>
          <li>
            <strong className="num">{c.pending}</strong> waiting in the queue
          </li>
          <li>
            <strong className="num">{data.uses_30d}</strong> bonus uses in 30 days
          </li>
        </ul>
      )}
      <div className="lr-filters" role="tablist" aria-label="Show">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            className={`lr-filter${filter === id ? ' on' : ''}`}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && !data && <Skeleton lines={3} height={40} delayed />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.items.length === 0 && (
        <EmptyState title="Nothing here">No precedents with this status.</EmptyState>
      )}
      {data && data.items.length > 0 && (
        <ul className="lr-list">
          {data.items.map((p) => {
            const [tone, label] = TONE[p.status] ?? ['neutral', p.status]
            return (
              <li key={p.id} className="lr-item card">
                <div className="lr-head">
                  <span>
                    <strong>{loanLabel(p.loan_type)}</strong> · rules{' '}
                    <span className="mono">{p.rule_ids.join(', ') || 'none'}</span>
                  </span>
                  <StatusChip tone={tone}>{label}</StatusChip>
                </div>
                <p>{p.summary}</p>
                <p className="small muted">
                  Approved by {p.reviewed_by || 'unknown'} · valid until {day(p.valid_until)}
                  {p.days_left > 0 ? ` (${p.days_left} days left)` : ''} · used {p.times_used} time
                  {p.times_used === 1 ? '' : 's'}
                  {p.last_used ? `, last on ${when(p.last_used)}` : ''}
                  {p.cases.length ? ` · cases ${p.cases.join(', ')}` : ''}
                </p>
                {p.status === 'paused' && <p className="small lr-why">{p.paused_reason}</p>}
                {p.status === 'retired' && (
                  <p className="small muted">
                    Retired by {p.retired_by}: &ldquo;{p.retired_reason}&rdquo;
                  </p>
                )}
                {(p.status === 'approved' || p.status === 'paused') && (
                  <div className="lr-actions">
                    {p.status === 'paused' && (
                      <button
                        type="button"
                        className="btn"
                        onClick={() => setDialog({ kind: 'reconfirm', item: p })}
                      >
                        Confirm again…
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setDialog({ kind: 'retire', item: p })}
                    >
                      Retire…
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {dialog && (
        <ReasonDialog
          title={
            dialog.kind === 'retire' ? 'Retire this precedent?' : 'Confirm this precedent again?'
          }
          confirmLabel={dialog.kind === 'retire' ? 'Yes, retire' : 'Yes, confirm'}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={confirm}
        >
          <p>
            {dialog.kind === 'retire'
              ? 'It stops helping borderline cases now. Its summary stays in the audit trail.'
              : 'It helps borderline cases again until it expires. Check that the changed policy still supports it.'}
          </p>
        </ReasonDialog>
      )}
    </div>
  )
}
