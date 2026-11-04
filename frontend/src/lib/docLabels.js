export const DOC_LABEL = {
  pan_card: 'PAN card',
  aadhaar: 'Aadhaar card',
  photo: 'Photograph',
  payslip: 'Payslips',
  bank_statement: 'Bank statement',
  form16: 'Form 16',
  itr: 'Income tax return',
  pnl_balance_sheet: 'Profit and loss, balance sheet',
  gst_registration: 'GST registration',
  gst_returns: 'GST returns',
  udyam_certificate: 'Udyam certificate',
  business_proof: 'Business proof',
  sale_agreement: 'Sale agreement',
  title_deed: 'Title deed',
  encumbrance_certificate: 'Encumbrance certificate',
  approved_plan: 'Approved building plan',
  admission_letter: 'Admission letter',
  fee_structure: 'Fee structure',
  marksheet: 'Marksheet',
  dealer_invoice: 'Dealer invoice',
  driving_licence: 'Driving licence',
  rc_book: 'Registration certificate',
  insurance: 'Insurance policy',
  unknown: 'Not recognised',
  other: 'Other',
}

/** "payslip/form16" reads as "Payslips or Form 16". */
export const docLabel = (type) =>
  type
    .split('/')
    .map((t) => DOC_LABEL[t] || t.replaceAll('_', ' '))
    .join(' or ')

export const WHO = { primary: 'Applicant', co: 'Co-applicant' }
