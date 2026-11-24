import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import ReasonDialog from '../components/ReasonDialog'
import StatusChip from '../components/StatusChip'
import { ErrorState } from '../components/States'
import './AdminAiControlPage.css'
import { SectionLoader } from '../components/Loading'

const TABS = [
  ['models', 'Models'],
  ['keys', 'Keys'],
  ['prompts', 'Prompts'],
  ['settings', 'Settings'],
]
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const when = (t) => (t ? new Date(t).toLocaleString() : '')

/** Lines that are only in `a` (removed) or only in `b` (added); the rest are unchanged. */
export function diffLines(a, b) {
  const inA = new Set(a.split('\n'))
  const inB = new Set(b.split('\n'))
  return [
    ...a.split('\n').map((t) => ({ t, k: inB.has(t) ? 'same' : 'del' })),
    ...b.split('\n').flatMap((t) => (inA.has(t) ? [] : [{ t, k: 'add' }])),
  ].filter((l) => l.t.trim() !== '' || l.k === 'same')
}

function Tabs({ tab, setTab, dirty }) {
  return (
    <div className="ai-tabs" role="tablist" aria-label="AI control">
      {TABS.map(([id, label]) => (
        <button
          key={id}
          type="button"
          role="tab"
          id={`ai-tab-${id}`}
          aria-selected={tab === id}
          aria-controls="ai-panel"
          className={`ai-tab${tab === id ? ' on' : ''}`}
          onClick={() => setTab(id)}
        >
          {label}
          {dirty && (id === 'models' || id === 'settings') ? ' •' : ''}
        </button>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------- models
function ModelsTab({ data, cfg, setCfg }) {
  const keyOf = Object.fromEntries(data.providers.map((p) => [p.id, p]))
  const setRole = (role, patch) =>
    setCfg({ ...cfg, roles: { ...cfg.roles, [role]: { ...cfg.roles[role], ...patch } } })
  const label = (p) => `${keyOf[p].model}${keyOf[p].key_set ? '' : ' (no key)'}`
  return (
    <div className="ai-pane">
      <p className="muted">
        Each step of the pipeline asks for a role. If the first model fails or is busy, the next one
        in the list answers. Only the models listed here can be chosen, and a model with no key in{' '}
        <span className="mono">.env</span> cannot be used.
      </p>
      {data.roles.map(({ role, label: what }) => {
        const spec = cfg.roles[role]
        const used = new Set([spec.primary, ...spec.fallbacks])
        const free = data.providers.filter((p) => !used.has(p.id))
        return (
          <section key={role} className="card ai-role" aria-label={`Models for ${role}`}>
            <h3>{what}</h3>
            <div className="ai-chain">
              <label>
                <span className="small muted">First choice</span>
                <select
                  className="select"
                  aria-label={`First choice for ${role}`}
                  value={spec.primary}
                  onChange={(e) =>
                    setRole(role, {
                      primary: e.target.value,
                      fallbacks: spec.fallbacks.filter((f) => f !== e.target.value),
                    })
                  }
                >
                  {data.providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {label(p.id)}
                    </option>
                  ))}
                </select>
              </label>
              {spec.fallbacks.map((f, i) => (
                <label key={f}>
                  <span className="small muted">Then, if it fails ({i + 1})</span>
                  <span className="ai-fb">
                    <select
                      className="select"
                      aria-label={`Fallback ${i + 1} for ${role}`}
                      value={f}
                      onChange={(e) =>
                        setRole(role, {
                          fallbacks: spec.fallbacks.map((x, k) => (k === i ? e.target.value : x)),
                        })
                      }
                    >
                      {[keyOf[f], ...free].map((p) => (
                        <option key={p.id} value={p.id}>
                          {label(p.id)}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      aria-label={`Remove fallback ${i + 1} for ${role}`}
                      onClick={() =>
                        setRole(role, { fallbacks: spec.fallbacks.filter((_, k) => k !== i) })
                      }
                    >
                      Remove
                    </button>
                  </span>
                </label>
              ))}
            </div>
            {spec.fallbacks.length < data.max_fallbacks && free.length > 0 && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setRole(role, { fallbacks: [...spec.fallbacks, free[0].id] })}
              >
                Add a fallback
              </button>
            )}
          </section>
        )
      })}
      <section className="card ai-role" aria-label="Retries and timeouts">
        <h3>Retries and timeouts</h3>
        <div className="ai-numbers">
          {[
            ['num_retries', 'Retries on the same model'],
            ['timeout', 'Seconds to wait for an answer'],
            ['cooldown_time', 'Seconds to rest a failing model'],
          ].map(([k, text]) => (
            <label key={k}>
              <span className="small muted">{text}</span>
              <input
                className="input"
                type="number"
                aria-label={text}
                min={data.limits[k][0]}
                max={data.limits[k][1]}
                value={cfg.router[k]}
                onChange={(e) =>
                  setCfg({ ...cfg, router: { ...cfg.router, [k]: Number(e.target.value) } })
                }
              />
            </label>
          ))}
        </div>
      </section>
    </div>
  )
}

// --------------------------------------------------------------------------- keys
function KeysTab({ data }) {
  const [results, setResults] = useState({})
  async function test(id) {
    setResults((r) => ({ ...r, [id]: { running: true } }))
    try {
      const out = await api.post('/admin/ai/test-model', { provider: id })
      setResults((r) => ({ ...r, [id]: out }))
    } catch (e) {
      setResults((r) => ({ ...r, [id]: { ok: false, error: e.message } }))
    }
  }
  return (
    <div className="ai-pane">
      <p className="muted">
        API keys are kept in the <span className="mono">.env</span> file on the server, never in the
        database and never on this page. To add or change a key, edit that file and restart the
        server. Here you can see whether a key is set and test that it works.
      </p>
      <div className="card">
        <table className="ai-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Key in .env</th>
              <th>Status</th>
              <th>Test</th>
            </tr>
          </thead>
          <tbody>
            {data.providers.map((p) => {
              const r = results[p.id]
              return (
                <tr key={p.id}>
                  <td data-label="Model">
                    <span className="mono">{p.model}</span>
                  </td>
                  <td data-label="Key in .env" className="mono">
                    {p.key_env}
                  </td>
                  <td data-label="Status">
                    <StatusChip tone={p.key_set ? 'approve' : 'refer'}>
                      {p.key_set ? 'Key is set' : 'Key is missing'}
                    </StatusChip>
                  </td>
                  <td data-label="Test">
                    <button
                      type="button"
                      className="btn"
                      disabled={!p.key_set || r?.running}
                      aria-label={`Test ${p.model}`}
                      onClick={() => test(p.id)}
                    >
                      {r?.running ? 'Testing…' : 'Test'}
                    </button>{' '}
                    {r && !r.running && (
                      <span role="status" className={r.ok ? 'ai-ok' : 'ai-bad'}>
                        {r.ok ? `Works (${r.latency_ms} ms)` : `Failed: ${r.error || 'no reply'}`}
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- settings
function SettingsTab({ data, cfg, setCfg }) {
  const setRole = (role, patch) =>
    setCfg({ ...cfg, roles: { ...cfg.roles, [role]: { ...cfg.roles[role], ...patch } } })
  return (
    <div className="ai-pane">
      <section className="card ai-role">
        <h3>Use the models</h3>
        <label className="ai-check">
          <input
            type="checkbox"
            checked={cfg.llm_enabled}
            onChange={(e) => setCfg({ ...cfg, llm_enabled: e.target.checked })}
          />
          <span>
            Models are on. Turn this off to have the system write every explanation and summary
            itself, in code. Scores, bands and rules are never affected.
          </span>
        </label>
      </section>
      <section className="card ai-role">
        <h3>Temperature and length, per step</h3>
        <p className="muted small">
          Temperature 0 gives the most repeatable answers and is the safest for a bank. A higher
          value varies the wording more. The length limit caps how long an answer may be; leave it
          empty to use each step&apos;s own limit.
        </p>
        <table className="ai-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>Temperature</th>
              <th>Length limit (tokens)</th>
            </tr>
          </thead>
          <tbody>
            {data.roles.map(({ role }) => (
              <tr key={role}>
                <td data-label="Step">{role}</td>
                <td data-label="Temperature">
                  <input
                    className="input"
                    type="number"
                    step="0.1"
                    min={data.limits.temperature[0]}
                    max={data.limits.temperature[1]}
                    aria-label={`Temperature for ${role}`}
                    value={cfg.roles[role].temperature}
                    onChange={(e) => setRole(role, { temperature: Number(e.target.value) })}
                  />
                </td>
                <td data-label="Length limit (tokens)">
                  <input
                    className="input"
                    type="number"
                    min={data.limits.max_tokens[0]}
                    max={data.limits.max_tokens[1]}
                    aria-label={`Length limit for ${role}`}
                    value={cfg.roles[role].max_tokens ?? ''}
                    onChange={(e) =>
                      setRole(role, {
                        max_tokens: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

// --------------------------------------------------------------------------- history
function History({ data, onRestore }) {
  if (!data?.length) return null
  return (
    <section className="card ai-role" aria-label="History of changes">
      <h3>History</h3>
      <ul className="ai-history">
        {data.map((v, i) => (
          <li key={v.version}>
            <span>
              <strong>Version {v.version}</strong> · {v.by || 'unknown'} · {when(v.at)}
              {v.source === 'rollback' ? ` · restored version ${v.rolled_back_to}` : ''}
              <br />
              <span className="muted">{v.reason}</span>
            </span>
            {i > 0 && (
              <button type="button" className="btn btn-ghost" onClick={() => onRestore(v.version)}>
                Restore version {v.version}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

// --------------------------------------------------------------------------- prompts
function PromptEditor({ name, summary, onChanged }) {
  const { data, error, reload, loading } = useAsync(
    () => api.get(`/admin/ai/prompts/${name}`),
    [name],
  )
  const [text, setText] = useState(null)
  const [msg, setMsg] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)
  const [dialogError, setDialogError] = useState(null)

  useEffect(() => {
    if (data) setText(data.draft?.body ?? data.editable)
  }, [data])
  useEffect(() => {
    setResult(null)
    setMsg(null)
  }, [name])

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <SectionLoader label="Loading the prompt" />
  if (!data || text === null) return null

  const inUse = data.editable
  const saved = data.draft?.body ?? null
  const changed = text.trim() !== inUse.trim()
  const unsaved = saved === null ? changed : text.trim() !== saved.trim()
  const canPublish = data.draft && !unsaved && data.draft.tested

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
  const saveDraft = () =>
    call(async () => {
      await api.put(`/admin/ai/prompts/${name}/draft`, { body: text })
      setResult(null)
      reload()
      onChanged()
    })
  const discard = () =>
    call(async () => {
      await api.del(`/admin/ai/prompts/${name}/draft`)
      setText(inUse)
      setResult(null)
      reload()
      onChanged()
    })
  const test = () =>
    call(async () => {
      setResult(await api.post(`/admin/ai/prompts/${name}/test`))
      reload()
    })
  async function confirm(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      if (dialog.kind === 'publish') {
        await api.post(`/admin/ai/prompts/${name}/publish`, { reason, second_click: true })
      } else {
        await api.post(`/admin/ai/prompts/${name}/rollback`, {
          version: dialog.version,
          reason,
          second_click: true,
        })
      }
      setDialog(null)
      setResult(null)
      reload()
      onChanged()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ai-pane">
      <p className="muted">
        {data.role}. Version <strong>{data.version}</strong>
        {data.edited ? ' (edited by an admin)' : ' (the original text)'}.
      </p>
      <label className="ai-edit">
        <span>Instructions you can change</span>
        <textarea
          className="input mono"
          rows={12}
          aria-label={`Editable instructions for ${name}`}
          value={text}
          maxLength={data.max_chars}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="small muted">
          {text.length} of {data.max_chars} characters
        </span>
      </label>

      <section className="ai-locked" aria-label="Locked rules">
        <h4>Locked rules (always added after your text, not editable)</h4>
        <pre>{data.locked}</pre>
      </section>

      {changed && (
        <section className="card ai-diff" aria-label="What changes">
          <h4>What changes compared with the text in use</h4>
          <pre>
            {diffLines(inUse, text).map((l, i) => (
              <span key={i} className={`d-${l.k}`}>
                {l.k === 'add' ? '+ ' : l.k === 'del' ? '- ' : '  '}
                {l.t}
                {'\n'}
              </span>
            ))}
          </pre>
        </section>
      )}

      {msg && (
        <p className="field-error" role="alert">
          {msg}
        </p>
      )}
      {result && (
        <div className={`ai-result ${result.ok ? 'ok' : 'bad'}`} role="status">
          <strong>{result.ok ? 'The test passed.' : 'The test did not pass.'}</strong>{' '}
          {result.model && <span className="muted">Answered by {result.model}.</span>}
          {result.issues.length > 0 && (
            <ul>
              {result.issues.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          )}
          {result.preview && <pre className="small">{result.preview}</pre>}
        </div>
      )}

      <div className="ai-actions">
        <button type="button" className="btn" disabled={busy || !unsaved} onClick={saveDraft}>
          Save draft
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy || !data.draft || unsaved}
          onClick={test}
        >
          Test the draft
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !canPublish}
          title={canPublish ? undefined : 'Save the draft and run the test first.'}
          onClick={() => setDialog({ kind: 'publish' })}
        >
          Publish
        </button>
        {data.draft && (
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={discard}>
            Discard the draft
          </button>
        )}
      </div>
      {!data.draft?.tested && data.draft && (
        <p className="small muted">A draft can be published only after it passes the test.</p>
      )}

      <section className="card ai-role" aria-label="Versions">
        <h3>Versions</h3>
        <ul className="ai-history">
          <li>
            <span>
              <strong>Version {data.file_version}</strong> · the original text
            </span>
            {data.version !== data.file_version && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setDialog({ kind: 'rollback', version: data.file_version })}
              >
                Restore the original
              </button>
            )}
          </li>
          {data.versions.map((v) => (
            <li key={v.version}>
              <span>
                <strong>Version {v.version}</strong> · {v.by || 'unknown'} · {when(v.at)}
                {v.source === 'rollback' ? ` · restored version ${v.rolled_back_to}` : ''}
                <br />
                <span className="muted">{v.reason}</span>
              </span>
              {v.version !== data.version && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setDialog({ kind: 'rollback', version: v.version })}
                >
                  Restore version {v.version}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      {dialog && (
        <ReasonDialog
          title={dialog.kind === 'publish' ? 'Publish this prompt?' : 'Restore an older prompt?'}
          confirmLabel={dialog.kind === 'publish' ? 'Yes, publish' : 'Yes, restore'}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={confirm}
        >
          <p>
            Every case that starts after this will use the new text. Cases already running keep the
            one they started with. The locked rules stay as they are.
          </p>
        </ReasonDialog>
      )}
      {summary?.has_draft && !data.draft && null}
    </div>
  )
}

function PromptsTab({ data, reloadOverview }) {
  const [name, setName] = useState(data.prompts[0].name)
  return (
    <div className="ai-pane">
      <p className="muted">
        You can change how each step is asked to write. The rules that keep the answers safe (treat
        documents as data, never calculate, say &ldquo;recommended&rdquo;, no protected attributes,
        the reply format) are locked and are always added after your text.
      </p>
      <div className="ai-prompt-list" role="tablist" aria-label="Prompts">
        {data.prompts.map((p) => (
          <button
            key={p.name}
            type="button"
            role="tab"
            aria-selected={name === p.name}
            className={`ai-tab${name === p.name ? ' on' : ''}`}
            onClick={() => setName(p.name)}
          >
            {p.name}
            {p.edited ? ' (edited)' : ''}
            {p.has_draft ? ' •' : ''}
          </button>
        ))}
      </div>
      <PromptEditor
        name={name}
        summary={data.prompts.find((p) => p.name === name)}
        onChanged={reloadOverview}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- page
export default function AdminAiControlPage() {
  const { data, error, reload } = useAsync(() => api.get('/admin/ai'), [])
  // asked for at the same time as the settings, not after them, so the page opens in one wait
  const history = useAsync(() => api.get('/admin/ai/config/history'), [])
  const [tab, setTab] = useState('models')
  const [edits, setCfg] = useState(null) // null = nothing changed: the form shows what is saved
  const cfg = edits ?? data?.config ?? null
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState(null)
  const [done, setDone] = useState(null)

  useEffect(() => {
    setCfg(null) // fresh settings from the server replace unsaved changes, as before
  }, [data])
  const dirty = useMemo(() => Boolean(data && cfg && !same(cfg, data.config)), [data, cfg])

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return <SectionLoader label="Loading the AI settings" />

  async function confirm(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      const out =
        dialog.kind === 'save'
          ? await api.put('/admin/ai/config', { config: cfg, reason, second_click: true })
          : await api.post('/admin/ai/config/rollback', {
              version: dialog.version,
              reason,
              second_click: true,
            })
      setDialog(null)
      setDone(`Saved as version ${out.version}. New cases use it from now on.`)
      history.reload()
      reload()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ai-control">
      <header>
        <h1>AI control</h1>
        <p className="muted">
          Choose which models answer, tune them and edit how they are asked. Changes apply to cases
          that start afterwards; a case already running keeps what it began with. Scores, bands,
          rules, checks and the safety rules never change from here. Currently version{' '}
          <strong>{data.version || 'original'}</strong>.
        </p>
      </header>
      <Tabs tab={tab} setTab={setTab} dirty={dirty} />
      {dirty && (
        <div className="ai-dirty" role="status">
          <span>You have changes that are not saved.</span>
          <button type="button" className="btn" onClick={() => setCfg(null)}>
            Discard
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setDialog({ kind: 'save' })}
          >
            Review and save
          </button>
        </div>
      )}
      {done && !dirty && (
        <p className="ai-ok" role="status">
          {done}
        </p>
      )}
      <div id="ai-panel" role="tabpanel" aria-labelledby={`ai-tab-${tab}`}>
        {tab === 'models' && (
          <>
            <ModelsTab data={data} cfg={cfg} setCfg={setCfg} />
            <History
              data={history.data}
              onRestore={(version) => setDialog({ kind: 'rollback', version })}
            />
          </>
        )}
        {tab === 'keys' && <KeysTab data={data} />}
        {tab === 'prompts' && <PromptsTab data={data} reloadOverview={reload} />}
        {tab === 'settings' && <SettingsTab data={data} cfg={cfg} setCfg={setCfg} />}
      </div>
      {dialog && (
        <ReasonDialog
          title={
            dialog.kind === 'save' ? 'Save these changes?' : `Restore version ${dialog.version}?`
          }
          confirmLabel={dialog.kind === 'save' ? 'Yes, save' : 'Yes, restore'}
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(null)}
          onConfirm={confirm}
        >
          <p>
            Any model that is new for a step is tested first, and the change is refused if the test
            fails. Cases that start after this use the new settings.
          </p>
        </ReasonDialog>
      )}
    </div>
  )
}
