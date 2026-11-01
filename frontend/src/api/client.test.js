import { describe, expect, it } from 'vitest'
import { messageFrom } from './client'

describe('messageFrom', () => {
  it('passes a plain message through', () => {
    expect(messageFrom('KYC documents are missing: pan_card (primary).', 422)).toContain('pan_card')
  })

  it('turns validation errors into one readable line', () => {
    const detail = [
      { loc: ['body', 'applicants', 0, 'pan'], msg: 'String should match pattern' },
      { loc: ['body'], msg: 'Value error, a education loan needs a co-applicant' },
    ]
    expect(messageFrom(detail, 422)).toBe(
      'applicants > 0 > pan: String should match pattern; a education loan needs a co-applicant',
    )
  })

  it('falls back to the status code', () => {
    expect(messageFrom(undefined, 500)).toBe('The request failed (500).')
  })
})
