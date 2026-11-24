import { expect } from '@playwright/test'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
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
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

// 2-step keys of the seeded admin and auditor (backend/tests/e2e_server.py, TWO_STEP_KEYS)
export const TWO_STEP_KEYS = {
  'admin@example.test': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
  'auditor@example.test': 'KRSXG5CTMVZGK5DTKRSXG5CTMVZGK5DT',
}

function base32(text) {
  const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of text.replace(/[\s=]/g, '').toUpperCase())
    bits += abc.indexOf(ch).toString(2).padStart(5, '0')
  const bytes = []
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2))
  return Buffer.from(bytes)
}

/** The 6-digit code an authenticator app shows for `key` in 30-second step `step` (RFC 6238). */
export function totp(key, step = Math.floor(Date.now() / 30000)) {
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(step))
  const mac = crypto.createHmac('sha1', base32(key)).update(counter).digest()
  const offset = mac[mac.length - 1] & 0x0f
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}

// The server takes each code once, so a step is never typed twice. The steps used are kept in a
// file, not in memory: Playwright starts a new worker after a failed test.
const USED = path.join(os.tmpdir(), 'pramaan-e2e-two-step.json')
const stepNow = () => Math.floor(Date.now() / 30000)

function nextStep(key) {
  let used = {}
  try {
    used = JSON.parse(fs.readFileSync(USED, 'utf8'))
  } catch {
    /* first use */
  }
  const step = Math.max(stepNow(), (used[key] ?? -1) + 1)
  fs.writeFileSync(USED, JSON.stringify({ ...used, [key]: step }))
  return step
}

/** Type a fresh code for `key` on the code screen. Waits for the next 30 seconds if needed. */
export async function enterCode(page, key, button = 'Verify and sign in') {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const step = nextStep(key)
    // the server also takes the next step's code, so wait only when both are used
    if (step > stepNow() + 1) await page.waitForTimeout((step - 1) * 30000 - Date.now() + 200)
    await page.getByLabel('6-digit code').fill(totp(key, step))
    await page.getByRole('button', { name: button }).click()
    // done when the code box goes away; one retry with the next step if it was refused
    const refused = page.getByText('That code is not right')
    await expect(async () => {
      const gone = (await page.getByLabel('6-digit code').count()) === 0
      expect(gone || (await refused.isVisible())).toBe(true)
    }).toPass({ timeout: 15_000 })
    if (!(await refused.isVisible())) return
  }
}

export async function signIn(page, who) {
  const email = `${who}@example.test`
  await signInAs(page, email, PASSWORD)
  if (TWO_STEP_KEYS[email]) {
    await expect(page.getByRole('heading', { name: 'Enter your code' })).toBeVisible()
    await enterCode(page, TWO_STEP_KEYS[email])
  }
}

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
  await page.getByRole('radio', { name: /Fill in the form first/ }).click()
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
  const labelled = page.locator('.label-yourself')
  if (!(await labelled.getAttribute('open'))) await labelled.locator('summary').click()
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
