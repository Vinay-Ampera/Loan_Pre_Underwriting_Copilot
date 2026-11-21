import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import IndexTools from '../components/IndexTools'
import LearningsPanel from '../components/LearningsPanel'
import PolicyEditor from '../components/PolicyEditor'
import PolicyHistory from '../components/PolicyHistory'
import PolicyList from '../components/PolicyList'
import PolicyReader from '../components/PolicyReader'
import PolicySearch from '../components/PolicySearch'
import { ErrorState, Skeleton } from '../components/States'
import { day, policyLabel } from '../lib/policy'
import './KnowledgeBasePage.css'

const TABS = [
  ['policies', 'Policies'],
  ['learnings', 'Learnings'],
  ['tools', 'Search and index'],
]
const VIEWS = [
  ['read', 'Read'],
  ['change', 'Change'],
  ['history', 'History'],
]

function Tabs({ items, value, onChange, label, marks = {} }) {
  return (
    <div className="kb-tabs" role="tablist" aria-label={label}>
      {items.map(([id, text]) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={value === id}
          className={`kb-tab${value === id ? ' on' : ''}`}
          onClick={() => onChange(id)}
        >
          {text}
          {marks[id] ? <span className="kb-mark"> · {marks[id]}</span> : null}
        </button>
      ))}
    </div>
  )
}

function PolicyPanel({ loanType, onListChanged }) {
  const [view, setView] = useState('read')
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/knowledge/policies/${loanType}`),
    [loanType],
  )
  const changed = (goto) => {
    reload()
    onListChanged()
    if (typeof goto === 'string') setView(goto)
  }
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading && !data) return <Skeleton lines={6} delayed />
  if (!data) return null
  return (
    <section className="kb-panel" aria-label={policyLabel(loanType)}>
      <Tabs
        items={VIEWS}
        value={view}
        onChange={setView}
        label="Policy view"
        marks={{ change: data.draft ? 'draft' : null }}
      />
      {data.scheduled && view === 'read' && (
        <p className="kb-note small">
          Version <span className="mono">{data.scheduled.version}</span> is scheduled to replace
          this one on {day(data.scheduled.effective_from)}. See History.
        </p>
      )}
      {view === 'read' && <PolicyReader version={data.active} admin />}
      {view === 'change' && <PolicyEditor loanType={loanType} detail={data} onChanged={changed} />}
      {view === 'history' && <PolicyHistory detail={data} onChanged={changed} />}
    </section>
  )
}

/** Admin: the policy documents behind the Policy agent, the learnings, and the index tools. */
export default function KnowledgeBasePage() {
  const [tab, setTab] = useState('policies')
  const [loanType, setLoanType] = useState('common')
  const list = useAsync(() => api.get('/knowledge/policies'), [])
  return (
    <div className="kb-page">
      <header className="page-head">
        <h1>Knowledge base</h1>
        <p className="muted">
          The policy the Policy agent reads, and what the system has learned from officers&apos;
          overrides. Scoring numbers live in the rules file and do not change here.
        </p>
      </header>
      <Tabs items={TABS} value={tab} onChange={setTab} label="Knowledge base" />
      {tab === 'policies' && (
        <div className="kb-grid">
          {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
          {list.data && (
            <PolicyList policies={list.data} selected={loanType} onSelect={setLoanType} />
          )}
          <PolicyPanel key={loanType} loanType={loanType} onListChanged={list.reload} />
        </div>
      )}
      {tab === 'learnings' && <LearningsPanel />}
      {tab === 'tools' && (
        <div className="kb-tools">
          <section className="card kb-search" aria-label="Search tester">
            <h4>Search tester</h4>
            <PolicySearch admin />
          </section>
          <IndexTools />
        </div>
      )}
    </div>
  )
}
