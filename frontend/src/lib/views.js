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
}

export const matchesView = (c, view) => !view || !VIEWS[view] || VIEWS[view].test(c)

export function tileCounts(cases) {
  return Object.fromEntries(
    Object.entries(VIEWS).map(([key, v]) => [key, cases.filter(v.test).length]),
  )
}
