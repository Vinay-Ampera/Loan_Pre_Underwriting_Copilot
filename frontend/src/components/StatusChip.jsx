import Icon from './Icons'
import './StatusChip.css'

const ICON = {
  approve: 'check',
  refer: 'alert-circle',
  reject: 'x',
  stopped: 'stop',
  unverified: 'help-circle',
  info: 'dot',
  running: 'loader',
  neutral: 'dot',
  done: 'check',
}

/** Label + icon + colour, never colour alone (DESIGN_SYSTEM principle 2). */
export default function StatusChip({ tone = 'neutral', children, title }) {
  return (
    <span className={`chip chip-${tone}`} title={title}>
      <span className={`chip-icon${tone === 'running' ? ' spin' : ''}`} aria-hidden="true">
        <Icon name={ICON[tone] || 'dot'} size={14} />
      </span>
      {children}
    </span>
  )
}

const CASE_STATUS = {
  draft: ['neutral', 'Draft'],
  uploaded: ['neutral', 'Documents uploaded'],
  applicant_submitted: ['info', 'Applicant submitted'],
  running: ['running', 'Assessing'],
  stopped: ['stopped', 'Stopped: needs correction'],
  confirmed: ['done', 'Confirmed by officer'],
  overridden: ['done', 'Overridden by officer'],
}
const BAND_TONE = { approve: 'approve', refer: 'refer', reject: 'reject' }

export function CaseStatusChip({ status, band }) {
  if (status === 'awaiting_confirmation') {
    return <StatusChip tone={BAND_TONE[band] || 'neutral'}>Awaiting confirmation</StatusChip>
  }
  const [tone, label] = CASE_STATUS[status] || ['neutral', status]
  return <StatusChip tone={tone}>{label}</StatusChip>
}

export function BandChip({ band }) {
  if (!band) return <StatusChip tone="stopped">Not computed</StatusChip>
  return <StatusChip tone={BAND_TONE[band]}>Recommended: {band}</StatusChip>
}
