import { expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
export const OUTPUT = path.resolve(here, '../../data/synthetic/output')
export const PASSWORD = 'e2e-password-123'

export function application(caseId) {
  return JSON.parse(fs.readFileSync(path.join(OUTPUT, 'cases', caseId, 'application.json'), 'utf8'))
}

/** The first dev case of a loan type that should run cleanly to the officer (no stop, no blurred IDs). */
export function cleanCase(prefix) {
  const index = JSON.parse(fs.readFileSync(path.join(OUTPUT, 'index.json'), 'utf8'))
  for (const c of index) {
    if (c.split !== 'dev' || !c.case_id.includes(`-${prefix}-`)) continue
    const key = JSON.parse(
      fs.readFileSync(path.join(OUTPUT, 'cases', c.case_id, 'answer_key.json'), 'utf8'),
    )
    if (key.expected_stop_stage === null && key.documents.every((d) => d.quality !== 'poor'))
      return c.case_id
  }
  throw new Error(`no clean dev case for ${prefix}`)
}

export async function signInAs(page, email, password) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

export const signIn = (page, who) => signInAs(page, `${who}@example.test`, PASSWORD)

async function fillPerson(page, prefix, a) {
  const set = (name, value) =>
    value == null ? Promise.resolve() : page.locator(`#${prefix}-${name}`).fill(String(value))
  await set('full_name', a.full_name)
  await set('dob', a.dob)
  await set('pan', a.pan)
  await set('aadhaar_last4', a.aadhaar_last4)
  await set('phone', a.phone)
  await set('address', a.address)
  await page.locator(`#${prefix}-employment_type`).selectOption(a.employment_type)
  if (a.employment_type !== 'student') {
    await set('employer_or_business', a.employer_or_business)
    await set('declared_monthly_income', a.declared_monthly_income)
    await set('months_in_current_employment', a.months_in_current_employment)
    await set('total_experience_months', a.total_experience_months)
  }
  await page
    .locator(`#${prefix}-residential_status`)
    .selectOption(a.residential_status === 'NRI' ? 'NRI' : 'resident')
  if (a.role === 'co') await set('relationship_to_primary', a.relationship_to_primary)
}

/** Loan type card, then the whole application form, then "Create case". Returns the workspace URL. */
export async function createCase(page, caseId, loanLabel) {
  const app = application(caseId)
  await page.getByRole('link', { name: 'New case' }).first().click()
  await page.getByRole('radio', { name: new RegExp(loanLabel) }).click()
  await page.locator('#f-amount').fill(String(app.loan_amount))
  await page.locator('#f-tenure').fill(String(app.tenure_months))
  await page.locator('#f-purpose').fill(app.purpose)
  await page.locator('#f-date').fill(app.application_date)
  for (const [name, value] of Object.entries(app.loan_details)) {
    const field = page.locator(`#d-${name}`)
    if (typeof value === 'boolean') await field.selectOption(value ? 'yes' : 'no')
    else if (await field.evaluate((el) => el.tagName === 'SELECT'))
      await field.selectOption(String(value))
    else await field.fill(String(value))
  }
  const [primary, co] = [app.applicants[0], app.applicants[1]]
  await fillPerson(page, 'p', primary)
  if (co) {
    const box = page.getByLabel('Add a co-applicant')
    if (await box.count()) await box.check()
    await fillPerson(page, 'c', co)
  }
  await page.getByRole('button', { name: 'Create case and add documents' }).click()
  await expect(page.getByRole('tab', { name: 'Documents' })).toBeVisible()
  return page.url()
}

/** Add every file of the case one by one, each with its own result row. */
export async function uploadAll(page, caseId) {
  const kinds = await page.locator('#up-kind option').evaluateAll((os) => os.map((o) => o.value))
  for (const role of ['primary', 'co']) {
    const dir = path.join(OUTPUT, 'cases', caseId, 'documents', role)
    if (!fs.existsSync(dir)) continue
    for (const file of fs.readdirSync(dir).sort()) {
      const stem = path.parse(file).name.replace(/[_-]\d.*$/, '')
      if (await page.locator('#up-role').count()) await page.locator('#up-role').selectOption(role)
      await page.locator('#up-kind').selectOption(kinds.includes(stem) ? stem : 'other')
      await page.locator('#up-files').setInputFiles(path.join(dir, file))
      const row = page.getByTestId('upload-results').locator('li', { hasText: file })
      await expect(row).toBeVisible()
      await expect(row).not.toContainText('Rejected')
    }
  }
}
