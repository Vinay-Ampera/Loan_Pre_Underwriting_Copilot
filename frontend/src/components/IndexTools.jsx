import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import ReasonDialog from './ReasonDialog'
import { ErrorState, Skeleton } from './States'
import { METRICS, day, pct, policyLabel, versionTone, when } from '../lib/policy'
import './IndexTools.css'

/**
 * The search index behind the Policy agent: what is embedded, which policy files are newer than
 * the database, a re-index from the files and the retrieval evaluation against its targets.
 */
export default function IndexTools() {
  const { data, error, loading, reload } = useAsync(() => api.get('/knowledge/index'), [])
  const [dialog, setDialog] = useState(false)
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [evalOut, setEvalOut] = useState(null)
  const [msg, setMsg] = useState(null)
  const [dialogError, setDialogError] = useState(null)

  async function reindex(reason) {
    setBusy(true)
    setDialogError(null)
    try {
      setResult(await api.post('/knowledge/index/reindex', { reason, second_click: true, force }))
      setDialog(false)
      reload()
    } catch (e) {
      setDialogError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function evaluate() {
    setBusy(true)
    setMsg(null)
    try {
      setEvalOut(await api.post('/knowledge/index/evaluate'))
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading && !data) return <Skeleton lines={4} />
  if (!data) return null
  return (
    <div className="index-tools">
      <section className="it-section card" aria-label="Index">
        <h4>Index</h4>
        <p className="small muted">
          Embeddings: <span className="mono">{data.settings.embedding_model}</span> · reranker:{' '}
          <span className="mono">{data.settings.reranker_model}</span> · top {data.settings.top_k}{' '}
          of {data.settings.candidates} candidates. Last re-index:{' '}
          {data.last_reindex
            ? `${when(data.last_reindex.at)} by ${data.last_reindex.by || 'the command line'}`
            : 'never'}
          .
        </p>
        <table className="it-table">
          <thead>
            <tr>
              <th scope="col">Policy</th>
              <th scope="col">Version</th>
              <th scope="col">State</th>
              <th scope="col">Clauses embedded</th>
            </tr>
          </thead>
          <tbody>
            {data.documents.map((d) => (
              <tr key={`${d.loan_type}-${d.version}`}>
                <td>{policyLabel(d.loan_type)}</td>
                <td className="mono">{d.version}</td>
                <td>
                  {versionTone(d.status)[1]}
                  {d.status === 'scheduled' ? ` (${day(d.effective_from)})` : ''}
                </td>
                <td className={`num${d.embedded < d.clauses ? ' it-bad' : ''}`}>
                  {d.embedded} of {d.clauses}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="it-section card" aria-label="Policy files">
        <h4>Policy files on the server</h4>
        <p className="small muted">
          The files in <span className="mono">data/policy</span> are the starting data. A re-index
          imports a file only when its version label is newer than every version here; versions you
          published on this screen are never overwritten by a file.
        </p>
        <ul className="it-files small">
          {data.files.map((f) => (
            <li key={f.file}>
              <span className="mono">{f.file}</span> {f.version} · {f.state}
            </li>
          ))}
        </ul>
        <div className="it-actions">
          <button type="button" className="btn" disabled={busy} onClick={() => setDialog(true)}>
            Re-index from the files…
          </button>
        </div>
        {result && (
          <ul className="it-files small" aria-label="Re-index result">
            {result.activated.map((lt) => (
              <li key={lt}>{policyLabel(lt)}: a scheduled version is now in force.</li>
            ))}
            {result.docs.map((d) => (
              <li key={d.loan_type}>
                {policyLabel(d.loan_type)} {d.version}:{' '}
                {d.note ||
                  `${d.added.length} added, ${d.changed.length} changed, ${d.removed.length} removed`}
              </li>
            ))}
            <li>{result.embedded} clause(s) embedded.</li>
          </ul>
        )}
      </section>

      <section className="it-section card" aria-label="Retrieval evaluation">
        <h4>Retrieval evaluation</h4>
        <p className="small muted">
          Runs the development questions against the policy in force and compares the result with
          the recorded targets. The held-out test questions are never run here.
        </p>
        {msg && (
          <p className="field-error" role="alert">
            {msg}
          </p>
        )}
        {evalOut && (
          <table className="it-table">
            <thead>
              <tr>
                <th scope="col">On {evalOut.metrics.queries} questions</th>
                <th scope="col">Now</th>
                <th scope="col">Target</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map(([k, label]) => (
                <tr key={k}>
                  <th scope="row">{label}</th>
                  <td
                    className={`num${evalOut.targets[k] !== undefined && evalOut.metrics[k] < evalOut.targets[k] ? ' it-bad' : ''}`}
                  >
                    {pct(evalOut.metrics[k])}
                  </td>
                  <td className="num">{pct(evalOut.targets[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {evalOut && (
          <p className="small">{evalOut.ok ? 'Every target is met.' : evalOut.misses.join('; ')}</p>
        )}
        <div className="it-actions">
          <button type="button" className="btn" disabled={busy} onClick={evaluate}>
            {busy ? 'Running…' : 'Run the evaluation'}
          </button>
        </div>
      </section>

      {dialog && (
        <ReasonDialog
          title="Re-index from the policy files?"
          confirmLabel="Yes, re-index"
          busy={busy}
          error={dialogError}
          onClose={() => setDialog(false)}
          onConfirm={reindex}
        >
          <p>
            Files with a newer version label are imported, and any scheduled version whose date has
            come is put in force. If a rule would lose its clause, nothing is changed.
          </p>
          <label className="it-check">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
            Embed every clause again (only after a change of embedding model)
          </label>
        </ReasonDialog>
      )}
    </div>
  )
}
