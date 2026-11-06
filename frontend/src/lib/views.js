// The four home tiles and the case-list views they open. Counting only: no scoring here.
export const VIEWS = {
  awaiting: { label: 'Awaiting confirmation', test: (c) => c.status === 'awaiting_confirmation' },
  referred: {
    label: 'Referred',
    test: (c) => c.status === 'awaiting_confirmation' && c.band === 'refer',
  },
  stopped: { label: 'Stopped', test: (c) => c.status === 'stopped' },
  progress: {
    label: 'In progress',
    test: (c) => ['draft', 'uploaded', 'running'].includes(c.status),
  },
  // not a tile: applicants who pressed Send to the bank and wait for the officer's review
  applicant: {
    label: 'From applicants, to review',
    test: (c) => c.origin === 'applicant' && c.status === 'applicant_submitted',
  },
  // not a tile: the notice on Home links here when an admin has changed one of the officer's cases
  corrected: { label: 'Changed by an admin', test: (c) => c.admin_corrected === true },
}

export const matchesView = (c, view) => !view || !VIEWS[view] || VIEWS[view].test(c)

export function tileCounts(cases) {
  return Object.fromEntries(
    Object.entries(VIEWS).map(([key, v]) => [key, cases.filter(v.test).length]),
  )
}
