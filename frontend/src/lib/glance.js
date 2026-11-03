// "At a glance": the few findings that matter most, picked from what the rules engine already
// produced. Order: hard fails, then band caps, then the biggest point losses. Nothing is scored here.
const RANK = { hard_fail: 0, cap: 1, points_lost: 2 }

export function topReasons(report, limit = 3) {
  return report.findings
    .filter((f) => f.severity in RANK)
    .map((f, i) => ({ f, i }))
    .sort(
      (a, b) =>
        RANK[a.f.severity] - RANK[b.f.severity] || b.f.points_lost - a.f.points_lost || a.i - b.i,
    )
    .slice(0, limit)
    .map(({ f }) => f)
}

// Citations narrowed by a text search and, optionally, by the stage of the finding that cites them.
export function filterCitations(report, { q = '', stage = '' } = {}) {
  const needle = q.trim().toLowerCase()
  const inStage = stage
    ? new Set(
        report.findings.filter((f) => f.stage === stage && f.clause_id).map((f) => f.clause_id),
      )
    : null
  return report.citations.filter(
    (c) =>
      (!inStage || inStage.has(c.clause_id)) &&
      (!needle ||
        c.clause_id.toLowerCase().includes(needle) ||
        c.text.toLowerCase().includes(needle)),
  )
}
