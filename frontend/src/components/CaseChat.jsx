import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { SectionLoader } from './Loading'
import { ErrorState } from './States'
import './CaseChat.css'

const EXAMPLE = 'Ask about this case, for example: Why did Income and FOIR lose points?'

function Citation({ cite, answer, open, onToggle }) {
  if (cite.kind === 'rule') return <code className="ref-id">{cite.id}</code>
  if (cite.kind === 'field') {
    return <span className="chat-field">{answer.fields?.[cite.id] ?? cite.id}</span>
  }
  return (
    <button
      type="button"
      className="ref-id chat-clause-chip"
      aria-expanded={open}
      onClick={onToggle}
    >
      {cite.id}
    </button>
  )
}

/** The sentences with their citation chips; a clause chip opens the clause under them. */
function Answer({ answer }) {
  const [open, setOpen] = useState(null)
  const clause = open && answer.clauses?.[open]
  return (
    <>
      <ul className="chat-sentences">
        {answer.sentences.map((s, i) => (
          <li key={i}>
            {s.text}{' '}
            <span className="chat-cites">
              {s.citations.map((c) => (
                <Citation
                  key={`${c.kind}:${c.id}`}
                  cite={c}
                  answer={answer}
                  open={open === c.id}
                  onToggle={() => setOpen(open === c.id ? null : c.id)}
                />
              ))}
            </span>
          </li>
        ))}
      </ul>
      {clause && (
        <aside className="chat-clause" aria-label={`Clause ${open}`}>
          <p>
            <code className="ref-id">{open}</code> <strong>{clause.title}</strong>
          </p>
          <p className="muted">{clause.text}</p>
        </aside>
      )}
      <p className="small muted">Check the cited source before relying on an answer.</p>
    </>
  )
}

function Turn({ turn, latestVersion }) {
  return (
    <li className="chat-turn">
      <p className="chat-question">
        <span className="sr-only">You asked: </span>
        {turn.question}
      </p>
      {turn.note && <p className="small muted">{turn.note}</p>}
      <div className="chat-answer">
        {turn.answer ? <Answer answer={turn.answer} /> : <p>{turn.text}</p>}
        {latestVersion != null && turn.report_version !== latestVersion && (
          <p className="small muted">About report version {turn.report_version}</p>
        )}
      </div>
    </li>
  )
}

/**
 * "Ask this case" (Stage 12 Part E): read-only questions about one case, for its officer and the
 * admin. The server decides every fixed text; nothing here changes the case, so no second click.
 */
export default function CaseChat({ caseId, reportVersion }) {
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/cases/${caseId}/chat`),
    [caseId, reportVersion],
  )
  const [added, setAdded] = useState([])
  const [question, setQuestion] = useState('')
  const [waiting, setWaiting] = useState(null)
  const [failed, setFailed] = useState(null)
  const end = useRef(null)
  useEffect(() => setAdded([]), [data])

  const turns = [...(data?.turns ?? []), ...added]
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' })
  }, [turns.length, waiting])

  if (loading && !data) return <SectionLoader label="Loading your questions" />
  if (error && !data) return <ErrorState error={error} onRetry={reload} />
  if (!data) return null

  const max = data.max_chars
  const ready = question.trim() && !waiting && !data.off

  async function ask() {
    if (!ready) return
    const asked = question.trim()
    setWaiting(asked)
    setFailed(null)
    try {
      const turn = await api.post(`/cases/${caseId}/chat`, { question: asked })
      setAdded((list) => [...list, turn])
      setQuestion('')
    } catch (e) {
      setFailed(e.message) // the question stays in the box
    } finally {
      setWaiting(null)
    }
  }

  return (
    <div className="chat">
      <p className="small muted">
        Answers come only from this case&apos;s report, its documents (personal numbers hidden) and
        the policy in force for this case. Chat cannot change the score or decide anything.
      </p>
      {data.off && (
        <p className="chat-off" role="status">
          {data.off_text}
        </p>
      )}
      <div className="chat-log fit-scroll" tabIndex={0} aria-label="Questions and answers">
        <ol className="chat-turns">
          {turns.map((t) => (
            <Turn key={t.id} turn={t} latestVersion={data.report_version} />
          ))}
        </ol>
        {waiting && (
          <>
            <p className="chat-question">{waiting}</p>
            <SectionLoader label="Reading the case" />
          </>
        )}
        <span ref={end} />
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault()
          ask()
        }}
      >
        <div className="field">
          <label htmlFor="chat-q">Your question</label>
          <textarea
            id="chat-q"
            className="textarea"
            rows={2}
            maxLength={max}
            placeholder={EXAMPLE}
            value={question}
            disabled={data.off}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                ask()
              }
            }}
          />
        </div>
        {failed && (
          <p className="field-error" role="alert">
            {failed}
          </p>
        )}
        <div className="chat-send">
          <span className="small muted">
            {question.length} of {max}
          </span>
          <button type="submit" className="btn btn-primary" disabled={!ready}>
            Ask
          </button>
        </div>
      </form>
    </div>
  )
}
