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

// Collateral has no score of its own. Where the rules file checks it, the check sits in the
// Policy fit stage: the loan-to-value limit for home and vehicle, the collateral needed above
// an amount for education. Personal and business loans have no collateral rule.
const COLLATERAL = {
  home: 'Loan-to-value limit, scored in Policy fit',
  vehicle: 'Loan-to-value limit, scored in Policy fit',
  education: 'Collateral above a set loan amount, scored in Policy fit',
}
export function collateralNote(loanType) {
  const note = COLLATERAL[loanType]
  return note
    ? { value: 'Checked in Policy fit', note }
    : { value: 'Not checked', note: 'No collateral rule for this loan type' }
}
