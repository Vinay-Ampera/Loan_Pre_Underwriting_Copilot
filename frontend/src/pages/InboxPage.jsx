import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useUnread } from '../components/UnreadProvider'
import { useAsync } from '../hooks/useAsync'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { formatWhen } from '../lib/format'
import './InboxPage.css'

const PAGE = 30
const FILTERS = [
  ['unread', 'Unread'],
  ['all', 'All'],
]

/**
 * The inbox of an officer (/inbox) or an admin (/admin/inbox). A notification carries a fixed
 * title, a case reference and a link: never a name, a number, a score or an outcome. Opening a
 * row marks it read and goes to the case (or to the Issues or Precedents page).
 */
export default function InboxPage() {
  const [filter, setFilter] = useState('unread')
  const [group, setGroup] = useState('')
  const [groups, setGroups] = useState([]) // the groups this role can receive, sent by the server
  const [typed, setTyped] = useState('')
  const [caseQ, setCaseQ] = useState('')

  // the case-number search waits for a pause in typing, and only sends what a number can hold
  useEffect(() => {
    const id = setTimeout(
      () =>
        setCaseQ(
          typed
            .trim()
            .toUpperCase()
            .replace(/[^A-Z0-9-]/g, ''),
        ),
      300,
    )
    return () => clearTimeout(id)
  }, [typed])

  const filtered = Boolean(group || caseQ)
  return (
    <div className="inbox">
      <header>
        <h1>Inbox</h1>
        <p className="muted">
          What needs your attention. A notice names the case, never the applicant.
        </p>
      </header>
      <div className="tabs" role="tablist" aria-label="Show">
        {FILTERS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={filter === key}
            className={`tab${filter === key ? ' on' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="inbox-filters" role="search" aria-label="Filter notifications">
        {groups.length > 0 && (
          <div className="field">
            <label htmlFor="inbox-group">Type</label>
            <select
              id="inbox-group"
              className="select"
              value={group}
              onChange={(e) => setGroup(e.target.value)}
            >
              <option value="">All types</option>
              {groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="inbox-case">Case number</label>
          <input
            id="inbox-case"
            type="search"
            className="input mono"
            placeholder="CASE-2026-0001"
            autoComplete="off"
            maxLength={14}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
        </div>
        {filtered && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setGroup('')
              setTyped('')
              setCaseQ('')
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <InboxList
        key={`${filter}|${group}|${caseQ}`}
        unreadOnly={filter === 'unread'}
        group={group}
        caseQ={caseQ}
        filtered={filtered}
        onGroups={setGroups}
      />
    </div>
  )
}

function InboxList({ unreadOnly, group, caseQ, filtered, onGroups }) {
  const navigate = useNavigate()
  const { count, setCount } = useUnread()
  const query = (offset) => {
    const q = new URLSearchParams({ limit: PAGE, offset, unread: unreadOnly })
    if (group) q.set('group', group)
    if (caseQ) q.set('case', caseQ)
    return `/notifications?${q}`
  }
  const { data, error, loading, reload } = useAsync(
    () => api.get(query(0)),
    [unreadOnly, group, caseQ],
  )
  useEffect(() => {
    if (data?.groups) onGroups(data.groups)
  }, [data, onGroups])
  const [more, setMore] = useState([])
  const [read, setRead] = useState({}) // ids marked read here: they stay in the list, greyed
  const [problem, setProblem] = useState(null)
  const [busy, setBusy] = useState(false)

  const items = data ? [...data.items, ...more] : []
  const isRead = (n) => Boolean(n.read_at) || read[n.id]
  const unreadHere = items.filter((n) => !isRead(n)).length

  async function mark(n) {
    if (isRead(n)) return
    setProblem(null)
    try {
      await api.post(`/notifications/${n.id}/read`)
      setRead((r) => ({ ...r, [n.id]: true }))
      setCount((c) => Math.max(0, c - 1))
    } catch (e) {
      setProblem(e.message)
    }
  }
  async function open(n) {
    await mark(n)
    if (n.path) navigate(n.path)
  }
  async function markAll() {
    setBusy(true)
    setProblem(null)
    try {
      const done = await api.post('/notifications/read-all')
      setRead(Object.fromEntries(items.map((n) => [n.id, true])))
      setCount(done.unread)
    } catch (e) {
      setProblem(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function showMore() {
    setBusy(true)
    setProblem(null)
    try {
      const next = await api.get(query(PAGE + more.length))
      setMore((m) => [...m, ...next.items])
    } catch (e) {
      setProblem(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <Skeleton lines={4} height={56} delayed />
  if (error) return <ErrorState error={error} onRetry={reload} />
  return (
    <>
      <div className="inbox-tools">
        <p className="small muted" aria-live="polite">
          {count === 0 ? 'Nothing unread.' : `${count} unread`}
        </p>
        <button type="button" className="btn" disabled={busy || unreadHere === 0} onClick={markAll}>
          Mark all read
        </button>
      </div>
      {problem && (
        <p className="field-error" role="alert">
          {problem}
        </p>
      )}
      {items.length === 0 ? (
        <EmptyState
          title={
            filtered
              ? 'Nothing matches these filters'
              : unreadOnly
                ? 'You are all caught up'
                : 'No notifications yet'
          }
        >
          {filtered
            ? 'Clear the filters to see everything.'
            : unreadOnly
              ? 'New notices appear here when something needs you.'
              : 'Notices appear here when an applicant sends files, a run finishes or an admin writes to you.'}
        </EmptyState>
      ) : (
        <ul className="card inbox-rows" aria-label="Notifications">
          {items.map((n) => (
            <li key={n.id} className={isRead(n) ? 'read' : 'unread'}>
              <button type="button" className="inbox-open" onClick={() => open(n)}>
                <span className="inbox-dot" aria-hidden="true" />
                <span className="inbox-text">
                  <span className="inbox-title">
                    {!isRead(n) && <span className="sr-only">Unread: </span>}
                    {n.title}
                  </span>
                  {n.body && <span className="small muted">{n.body}</span>}
                  <span className="small muted">
                    {n.case_ref && `${n.case_ref} · `}
                    {formatWhen(n.created_at)}
                  </span>
                </span>
              </button>
              {!isRead(n) && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  aria-label={`Mark read: ${n.title}`}
                  onClick={() => mark(n)}
                >
                  Mark read
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.total > PAGE + more.length && (
        <button type="button" className="btn inbox-more" disabled={busy} onClick={showMore}>
          Show more
        </button>
      )}
    </>
  )
}
