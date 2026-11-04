import './StatusChip.css'

const ICON = {
  approve: '✓',
  refer: '!',
  reject: '✕',
  stopped: '■',
  unverified: '?',
  info: '⟳',
  neutral: '●',
  done: '✓',
}

/** Label + icon + colour, never colour alone (DESIGN_SYSTEM principle 2). */
export default function StatusChip({ tone = 'neutral', children, title }) {
  return (
    <span className={`chip chip-${tone}`} title={title}>
      <span className={`chip-icon${tone === 'info' ? ' spin' : ''}`} aria-hidden="true">
        {ICON[tone]}
      </span>
      {children}
    </span>
  )
}

const CASE_STATUS = {
  draft: ['neutral', 'Draft'],
  uploaded: ['neutral', 'Documents uploaded'],
  applicant_submitted: ['info', 'Applicant submitted'],
  running: ['info', 'Assessing'],
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
