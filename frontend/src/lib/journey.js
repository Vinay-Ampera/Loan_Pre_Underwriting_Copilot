// The five underwriting stages shown on the login page and as the stepper on a case
// (DESIGN_SYSTEM section 8.5). Agent names appear only as small detail text.
export const JOURNEY = [
  {
    id: 'intake',
    label: 'Application intake and screening',
    detail: 'Upload checks, extraction, duplicate check',
    points: null,
    pipeline: 'extraction',
  },
  {
    id: 'verify',
    label: 'Verification and documents',
    detail: 'KYC and document checks',
    points: 'KYC 20 · Documents 15',
    pipeline: 'kyc',
  },
  {
    id: 'risk',
    label: 'Risk and ratios',
    detail: 'Income and FOIR, credit and behaviour',
    points: 'Income and FOIR 30 · Credit 25',
    pipeline: 'risk',
  },
  {
    id: 'decision',
    label: 'Decisioning and conditions',
    detail: 'Policy fit and the recommendation',
    points: 'Policy fit 10',
    pipeline: 'policy',
  },
  {
    id: 'signoff',
    label: 'Officer sign-off',
    detail: 'A human confirms or overrides',
    points: null,
    pipeline: null,
  },
]

const STOP_INDEX = { extraction: 0, kyc: 1, risk: 2, policy: 3 }

/**
 * Where the case is. Returns one entry per stage with a state:
 * done | current | stopped | todo. Stage 5 is the human and is never "done" by the system:
 * it is done only once an officer has confirmed or overridden.
 */
export function journeyState(c) {
  const ran = new Set((c.stages || []).map((s) => s.stage))
  const stoppedAt = c.status === 'stopped' ? STOP_INDEX[c.report?.stopped_stage] : undefined
  let doneCount
  if (c.status === 'confirmed' || c.status === 'overridden') doneCount = 5
  else if (c.status === 'awaiting_confirmation') doneCount = 4
  else if (c.status === 'stopped') doneCount = stoppedAt ?? 0
  else if (c.status === 'running') {
    const finished = [
      ran.has('extraction'),
      ran.has('kyc'),
      ran.has('risk'),
      ran.has('policy') && ran.has('decision'),
    ]
    doneCount = 0
    while (doneCount < 4 && finished[doneCount]) doneCount++
  } else doneCount = 0
  return JOURNEY.map((stage, i) => {
    let state = 'todo'
    if (i < doneCount) state = 'done'
    else if (i === doneCount) state = c.status === 'stopped' ? 'stopped' : 'current'
    return { ...stage, state }
  })
}
