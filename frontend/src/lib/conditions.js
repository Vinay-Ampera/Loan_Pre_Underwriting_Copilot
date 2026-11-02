// Conditions: what the officer still needs to obtain or fix. Taken from the document-stage
// findings the rules engine already produced; nothing is scored or computed here.
export function conditionsFrom(report) {
  return report.findings.filter((f) => f.stage === 'documents' && f.severity !== 'note')
}

// Credit / Capacity / Collateral: a display-only regrouping of existing stage scores.
export function threeC(report) {
  const row = (stage) => report.stage_scores.find((s) => s.stage === stage)
  const pick = (r) => (r && r.ran ? { score: r.score, max: r.max } : null)
  return {
    credit: pick(row('credit')),
    capacity: pick(row('income')),
    collateral: null,
  }
}
