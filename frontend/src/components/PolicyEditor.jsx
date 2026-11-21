import { useEffect, useState } from 'react'
import { api } from '../api/client'
import CheckReport from './CheckReport'
import ClauseDiff from './ClauseDiff'
import ConfirmDialog from './ConfirmDialog'
import ReasonDialog from './ReasonDialog'
import { METRICS, SOURCES, TOPICS, originLabel, pct, policyLabel, when } from '../lib/policy'
import './PolicyEditor.css'

const MODES = [
  ['clauses', 'One clause at a time'],
  ['text', 'Whole text'],
  ['upload', 'Upload a file'],
]

function ClauseForm({ clause, clauses, onSave, onCancel, busy }) {
  const isNew = !clause
  const [f, setF] = useState({
    source_tag: clause?.source_tag ?? 'sample',
    title: clause?.title ?? '',
    text: clause?.text ?? '',
    topic: 'ELIG',
    clause_id: '',
    after: clauses.at(-1)?.clause_id ?? '',
  })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const ok = f.title.trim() && f.text.trim()
  return (
    <form
      className="pe-form card"
      aria-label={isNew ? 'New clause' : `Edit ${clause.clause_id}`}
      onSubmit={(e) => {
        e.preventDefault()
        onSave(
          isNew
            ? {
                action: 'add',
                source_tag: f.source_tag,
                title: f.title,
                text: f.text,
                after: f.after || null,
                ...(f.clause_id.trim() ? { clause_id: f.clause_id.trim() } : { topic: f.topic }),
              }
            : {
                action: 'edit',
                clause_id: clause.clause_id,
                source_tag: f.source_tag,
                title: f.title,
                text: f.text,
              },
        )
      }}
    >
      {isNew && (
        <div className="pe-row">
          <label className="field">
            <span className="field-label">Topic (for the new clause ID)</span>
            <select className="select" value={f.topic} onChange={set('topic')}>
              {TOPICS.map(([id, label]) => (
                <option key={id} value={id}>
                  {label} ({id})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Or type the clause ID</span>
            <input
              className="input mono"
              value={f.clause_id}
              onChange={set('clause_id')}
              placeholder="leave empty for the next free ID"
              maxLength={20}
            />
          </label>
          <label className="field">
            <span className="field-label">Place it after</span>
            <select className="select" value={f.after} onChange={set('after')}>
              {clauses.map((c) => (
                <option key={c.clause_id} value={c.clause_id}>
                  {c.clause_id} {c.title}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className="pe-row">
        <label className="field">
          <span className="field-label">Source</span>
          <select className="select" value={f.source_tag} onChange={set('source_tag')}>
            {SOURCES.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field pe-grow">
          <span className="field-label">Title</span>
          <input className="input" value={f.title} onChange={set('title')} maxLength={200} />
        </label>
      </div>
      <label className="field">
        <span className="field-label">Clause text</span>
        <textarea className="textarea" rows={4} value={f.text} onChange={set('text')} />
      </label>
      <div className="pe-actions">
        <button type="submit" className="btn btn-primary" disabled={busy || !ok}>
          {isNew ? 'Add to the draft' : 'Save to the draft'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function Retrieval({ draft, busy, onRun }) {
  const r = draft.retrieval
  return (
    <section className="pe-section card" aria-label="Retrieval check">
      <h4>Retrieval check</h4>
      <p className="small muted">
        Runs the evaluation questions for this policy against the version in force and against the
        draft, so you can see whether search still finds the right clauses.
      </p>
      {draft.retrieval_stale && (
        <p className="small">The text changed after the last check. Run it again.</p>
      )}
      {r && (
        <>
          <table className="pe-table">
            <caption className="sr-only">Search quality, in force and draft</caption>
            <thead>
              <tr>
                <th scope="col">On {r.queries} questions</th>
                <th scope="col">In force</th>
                <th scope="col">Draft</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map(([k, label]) => (
                <tr key={k}>
                  <th scope="row">{label}</th>
                  <td className="num">{pct(r.now[k])}</td>
                  <td className={`num${r.draft[k] < r.now[k] ? ' pe-worse' : ''}`}>
                    {pct(r.draft[k])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {[...r.errors, ...r.warnings].map((m) => (
            <p key={m} className={r.errors.includes(m) ? 'field-error' : 'small'}>
              {m}
            </p>
          ))}
        </>
      )}
      <div>
        <button type="button" className="btn" disabled={busy || !draft.check.ok} onClick={onRun}>
          {r && !draft.retrieval_stale
            ? 'Run the retrieval check again'
            : 'Run the retrieval check'}
        </button>
      </div>
    </section>
  )
}

function Upload({ loanType, hasDraft, busy, call, onUse }) {
  const [got, setGot] = useState(null)
  const [legacy, setLegacy] = useState(null)
  const [checked, setChecked] = useState(false)
  async function pick(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append('loan_type', loanType)
    form.append('file', file)
    setLegacy(null)
    setChecked(false)
    const out = await call(() => api.upload('/knowledge/convert', form))
    setGot(out)
  }
  async function asLegacy() {
    setLegacy(
      await call(() => api.post('/knowledge/legacy', { loan_type: loanType, body: got.text })),
    )
  }
  return (
    <div className="pe-pane">
      <label className="field">
        <span className="field-label">A .md, .txt or .docx file (up to 1 MB)</span>
        <input
          type="file"
          accept=".md,.markdown,.txt,.docx"
          onChange={pick}
          disabled={busy}
          aria-describedby="upload-help"
        />
      </label>
      <p id="upload-help" className="small muted">
        Word and text files are turned into the policy format here. Nothing is saved until you
        choose to use the result as the draft{hasDraft ? ', which replaces your current draft' : ''}
        .
      </p>
      {got && (
        <div className="pe-section card">
          <h4>Converted text</h4>
          {got.notes.map((n) => (
            <p key={n} className="small muted">
              {n}
            </p>
          ))}
          <p className="small">
            {got.check.errors.length} error(s), {got.check.warnings.length} warning(s)
            {got.check.fixes.length ? `, ${got.check.fixes.length} formatting fix(es) offered` : ''}
            .
          </p>
          <pre className="pe-preview">{got.text}</pre>
          {got.suggest_legacy && !legacy && (
            <p className="small">
              No clause headings were found. If this is an older policy without clause IDs, import
              it as an old-format document: each heading becomes a clause.
            </p>
          )}
          <div className="pe-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => onUse(got.text, 'upload')}
            >
              Use this as the draft
            </button>
            <button type="button" className="btn" disabled={busy} onClick={asLegacy}>
              Import as an old-format document
            </button>
          </div>
        </div>
      )}
      {legacy && (
        <div className="pe-section card">
          <h4>Headings found and the clause IDs proposed</h4>
          <table className="pe-table">
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col">Heading</th>
                <th scope="col">Clause</th>
                <th scope="col">How</th>
              </tr>
            </thead>
            <tbody>
              {legacy.mapping.map((m) => (
                <tr key={`${m.line}-${m.heading}`}>
                  <td className="num">{m.line}</td>
                  <td>{m.heading}</td>
                  <td className="mono">{m.clause_id ?? ''}</td>
                  <td>
                    {
                      {
                        kept: 'ID written in the document',
                        matched: `same title as ${m.matched}`,
                        new: 'new ID, please check',
                        skipped: 'part title, no text: left out',
                      }[m.how]
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <label className="pe-check">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            I have checked every clause ID in this table. Rules and old reports find clauses by ID.
          </label>
          <div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !checked}
              onClick={() => onUse(legacy.text, 'legacy')}
            >
              Use this as the draft
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Change a policy: always through a draft, checked, compared and confirmed before it counts. */
export default function PolicyEditor({ loanType, detail, onChanged }) {
  const draft = detail.draft
  const [mode, setMode] = useState('clauses')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [editing, setEditing] = useState(null)
  const [text, setText] = useState(draft?.body ?? '')
  const [dialog, setDialog] = useState(null)
  const [ack, setAck] = useState(false)
  const [dialogError, setDialogError] = useState(null)

  useEffect(() => setText(draft?.body ?? ''), [draft?.body])

  const base = `/knowledge/policies/${loanType}/draft`
  const clauses = draft?.clauses ?? (draft ? [] : (detail.active?.clause_list ?? []))

  async function call(fn) {
    setBusy(true)
    setMsg(null)
    try {
      return await fn()
    } catch (e) {
      setMsg(e.message)
      return null
    } finally {
      setBusy(false)
    }
  }
  const after = async (p) => {
    if ((await p) !== null) onChanged()
  }
  const save = (body, origin = 'edit') =>
    after(call(() => api.put(base, { body, origin }).then(() => setEditing(null))))
  const editClause = (payload) =>
    after(call(() => api.post(`${base}/clause`, payload).then(() => setEditing(null))))
  const startText = () => after(call(() => api.post(`${base}/start`)))
  const runCheck = () => after(call(() => api.post(`${base}/retrieval-check`)))

  async function confirm(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      if (dialog.kind === 'publish') {
        await api.post(`${base}/publish`, { reason, second_click: true, accept_warnings: ack })
      }
      setDialog(null)
      setAck(false)
      onChanged()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function confirmPlain() {
    setBusy(true)
    setDialogError(null)
    try {
      if (dialog.kind === 'discard') await api.del(base)
      if (dialog.kind === 'remove')
        await api.post(`${base}/clause`, { action: 'remove', clause_id: dialog.clause })
      if (dialog.kind === 'replace')
        await api.put(base, { body: dialog.body, origin: dialog.origin })
      setDialog(null)
      onChanged()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }
  const useUploaded = (body, origin) =>
    draft ? setDialog({ kind: 'replace', body, origin }) : save(body, origin)

  const summary = draft?.check.summary
  const scheduled = summary?.takes_effect === 'scheduled'
  const unsaved = draft ? text !== draft.body : false

  return (
    <div className="policy-editor">
      {draft ? (
        <div className="pe-bar" role="status">
          <span>
            <strong>Draft</strong> · {originLabel(draft.origin)} · saved by {draft.updated_by} on{' '}
            {when(draft.updated_at)}. Officers and cases still use the version in force.
          </span>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy}
            onClick={() => setDialog({ kind: 'discard' })}
          >
            Discard the draft
          </button>
        </div>
      ) : (
        <p className="muted">
          There is no draft. Change a clause, edit the whole text or upload a file to start one;
          nothing reaches officers or cases until you publish it.
        </p>
      )}

      <div className="pe-tabs" role="tablist" aria-label="How to change the policy">
        {MODES.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            className={`pe-tab${mode === id ? ' on' : ''}`}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {msg && (
        <p className="field-error" role="alert">
          {msg}
        </p>
      )}

      {mode === 'clauses' && (
        <div className="pe-pane">
          {draft && !draft.clauses && (
            <p className="small">
              The draft has errors that stop it being read clause by clause. Fix them in the whole
              text, or apply the fixes below.
            </p>
          )}
          <ul className="pe-clauses">
            {clauses.map((c) =>
              editing === c.clause_id ? (
                <li key={c.clause_id}>
                  <ClauseForm
                    clause={c}
                    clauses={clauses}
                    busy={busy}
                    onSave={editClause}
                    onCancel={() => setEditing(null)}
                  />
                </li>
              ) : (
                <li key={c.clause_id} className="pe-clause">
                  <div>
                    <span className="mono ref-id">{c.clause_id}</span> <strong>{c.title}</strong>{' '}
                    <span className="small muted">({c.source_tag})</span>
                    <p className="small">{c.text}</p>
                  </div>
                  <div className="pe-clause-actions">
                    <button
                      type="button"
                      className="btn btn-ghost"
                      aria-label={`Change ${c.clause_id}`}
                      disabled={busy}
                      onClick={() => setEditing(c.clause_id)}
                    >
                      Change
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      aria-label={`Remove ${c.clause_id}`}
                      disabled={busy}
                      onClick={() => setDialog({ kind: 'remove', clause: c.clause_id })}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ),
            )}
          </ul>
          {editing === 'new' ? (
            <ClauseForm
              clause={null}
              clauses={clauses}
              busy={busy}
              onSave={editClause}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <div>
              <button
                type="button"
                className="btn"
                disabled={busy || (draft && !draft.clauses)}
                onClick={() => setEditing('new')}
              >
                Add a clause
              </button>
            </div>
          )}
        </div>
      )}

      {mode === 'text' && (
        <div className="pe-pane">
          {draft ? (
            <>
              <label className="field">
                <span className="field-label">The whole policy text (Markdown)</span>
                <textarea
                  className="textarea mono pe-text"
                  rows={22}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  spellCheck={false}
                />
              </label>
              <p className="small muted">
                Front matter at the top, then one clause per heading:{' '}
                <span className="mono">## HL-ELIG-01 | public | Age and tenure</span>.
              </p>
              <div className="pe-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy || !unsaved}
                  onClick={() => save(text)}
                >
                  Save the draft
                </button>
                {unsaved && <span className="small">You have changes that are not saved.</span>}
              </div>
            </>
          ) : (
            <button type="button" className="btn" disabled={busy} onClick={startText}>
              Start a draft from the version in force
            </button>
          )}
        </div>
      )}

      {mode === 'upload' && (
        <Upload
          loanType={loanType}
          hasDraft={Boolean(draft)}
          busy={busy}
          call={call}
          onUse={useUploaded}
        />
      )}

      {draft && (
        <>
          <CheckReport
            check={draft.check}
            busy={busy}
            onApplyFixes={draft.check.fixed_text ? () => save(draft.check.fixed_text) : null}
          />
          {draft.check.changes && (
            <ClauseDiff changes={draft.check.changes} title="Compared with the version in force" />
          )}
          <Retrieval draft={draft} busy={busy} onRun={runCheck} />
          <section className="pe-section card" aria-label="Publish">
            <h4>{scheduled ? 'Schedule' : 'Publish'}</h4>
            {draft.blockers.length > 0 ? (
              <ul className="small pe-blockers">
                {draft.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            ) : (
              <p className="small muted">
                {scheduled
                  ? `Version ${summary.version} will take effect on ${summary.effective_from}. Cases that start before then keep the version in force.`
                  : `Version ${summary.version} takes effect at once for cases that start after you publish. Running cases and old reports keep the version they used.`}
              </p>
            )}
            <div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !draft.can_publish || unsaved}
                onClick={() => setDialog({ kind: 'publish' })}
              >
                {scheduled ? 'Schedule…' : 'Publish…'}
              </button>
            </div>
          </section>
        </>
      )}

      {dialog?.kind === 'publish' && (
        <ReasonDialog
          title={`${scheduled ? 'Schedule' : 'Publish'} the ${policyLabel(loanType).toLowerCase()} policy, version ${summary.version}?`}
          confirmLabel={scheduled ? 'Yes, schedule' : 'Yes, publish'}
          busy={busy}
          error={dialogError}
          blocked={draft.warning_count > 0 && !ack}
          onClose={() => {
            setDialog(null)
            setAck(false)
          }}
          onConfirm={confirm}
        >
          <p>
            {scheduled
              ? `It becomes the policy in force on ${summary.effective_from}.`
              : 'It becomes the policy in force for every case that starts from now on.'}{' '}
            Approved precedents whose rules use a changed clause are paused until you confirm them
            again.
          </p>
          {draft.warning_count > 0 && (
            <label className="pe-check">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I
              have read the {draft.warning_count} warning{draft.warning_count === 1 ? '' : 's'}.
            </label>
          )}
        </ReasonDialog>
      )}
      {dialog && dialog.kind !== 'publish' && (
        <ConfirmDialog
          title={
            dialog.kind === 'discard'
              ? 'Discard the draft?'
              : dialog.kind === 'remove'
                ? `Remove ${dialog.clause} from the draft?`
                : 'Replace the current draft?'
          }
          confirmLabel={
            dialog.kind === 'discard'
              ? 'Yes, discard'
              : dialog.kind === 'remove'
                ? 'Yes, remove'
                : 'Yes, replace'
          }
          danger={dialog.kind !== 'replace'}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={confirmPlain}
        >
          <p>
            {dialog.kind === 'discard'
              ? 'The draft text and its checks are deleted. The version in force is not touched.'
              : dialog.kind === 'remove'
                ? 'The clause leaves the draft only. Older versions keep it, and the check tells you if a rule still needs it.'
                : 'The uploaded text replaces the text of your current draft.'}
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
