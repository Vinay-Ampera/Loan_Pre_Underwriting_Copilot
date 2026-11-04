import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { application, cleanCase, OUTPUT, signIn } from './helpers'

// Stage 10, Parts A to C in the browser: documents first (a whole folder), the inventory, the
// identity fields filled from the cards and confirmed with a tick, the claims typed by hand, then
// an applicant's link used from a second browser context that has no sign-in.

test('documents first: folder, inventory, identity from the cards, claims by hand, submit', async ({
  page,
}) => {
  const caseId = cleanCase('PL')
  const app = application(caseId)
  const me = app.applicants[0]
  await signIn(page, 'officer')
  await page.getByRole('link', { name: 'New case' }).first().click()
  await page.getByRole('radio', { name: /Personal loan/ }).click()
  await page.getByRole('radio', { name: /Start with the documents/ }).click()
  await page.getByRole('button', { name: 'Open the case and add documents' }).click()
  await expect(page.getByRole('tab', { name: 'Documents' })).toBeVisible()
  // nothing is asked yet, and the form cannot be submitted before it exists
  await expect(page.getByRole('button', { name: 'Submit for assessment' })).toBeDisabled()

  await page.locator('#bulk-folder').setInputFiles(path.join(OUTPUT, 'cases', caseId, 'documents'))
  await expect(page.getByTestId('bulk-results')).toContainText('received', { timeout: 180_000 })
  const inventory = page.getByTestId('inventory')
  await expect(inventory).toContainText('Received')
  await expect(inventory.getByLabel('Type of pan_card.jpg')).toBeVisible()

  // employment is a claim: until it is stated, income papers are listed apart, not as missing
  await expect(inventory).toContainText('Depends on employment type')
  await page.getByLabel('Employment type of the applicant').selectOption(me.employment_type)
  await expect(inventory).not.toContainText('Depends on employment type')

  // Proceed anyway is not even offered: nothing is missing
  await expect(page.getByRole('button', { name: 'Proceed anyway' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Continue to the application form' }).click()

  // identity came from the cards; the claims did not
  await expect(page.locator('#p-full_name')).toHaveValue(me.full_name)
  await expect(page.locator('#p-pan')).toHaveValue(me.pan)
  await expect(page.locator('#f-amount')).toHaveValue('')
  await expect(page.locator('#p-declared_monthly_income')).toHaveValue('')
  await expect(page.locator('.from-doc').first()).toBeVisible()
  await page.locator('#f-amount').fill(String(app.loan_amount))
  await page.locator('#f-tenure').fill(String(app.tenure_months))
  await page.locator('#f-purpose').fill(app.purpose)
  await page.locator('#f-date').fill(app.application_date)
  await page.locator('#p-declared_monthly_income').fill(String(me.declared_monthly_income))
  await page.locator('#p-phone').fill(String(me.phone))

  // the tick is required
  await page.getByRole('button', { name: 'Save the form' }).click()
  await expect(page.getByText(/Tick the box to confirm/)).toBeVisible()
  await page.getByRole('checkbox', { name: /I confirmed the details/ }).check()
  await page.getByRole('button', { name: 'Save the form' }).click()

  const submit = page.getByRole('button', { name: 'Submit for assessment' })
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText('Awaiting confirmation').first()).toBeVisible({ timeout: 240_000 })
  await page.getByRole('tab', { name: 'Report' }).click()
  await expect(page.getByText('Identity details read from the cards')).toBeVisible()
  await expect(page.getByText('not an independent check').first()).toBeVisible()
  await expect(page.locator('body')).not.toContainText(/\b(is|was|been)\s+approved\b/i)
})

test('an applicant link: created with a second click, used with no sign-in, shown in the queue', async ({
  page,
  browser,
}) => {
  const caseId = cleanCase('PL')
  await signIn(page, 'officer')
  await page.getByRole('link', { name: 'Upload links' }).click()
  await page.getByRole('button', { name: 'Create a link' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Kind of loan').selectOption('personal')
  await dialog.getByRole('button', { name: 'Create the link' }).click() // the second click
  const address = await page.getByLabel('Upload link address').inputValue()
  expect(address).toMatch(/\/u#[A-Za-z0-9_-]{30,}$/)
  await page.getByRole('button', { name: 'Done' }).click()

  // the applicant: a fresh browser context, no cookies, no session
  const context = await browser.newContext()
  const guest = await context.newPage()
  await guest.goto(address)
  await expect(guest.getByRole('heading', { name: /Send your documents/ })).toBeVisible()
  await guest.getByLabel(/Amount you would like/).fill('250000')
  await guest.getByLabel(/For how many months/).fill('24')
  await guest.getByRole('button', { name: 'Save my request' }).click()
  await expect(guest.getByText('What to send')).toBeVisible()
  const dir = path.join(OUTPUT, 'cases', caseId, 'documents', 'primary')
  const pdfs = fs.readdirSync(dir).filter((f) => f.startsWith('payslip') && f.endsWith('.pdf'))
  await guest.locator('#bulk-files').setInputFiles(pdfs.map((f) => path.join(dir, f)))
  await expect(guest.getByTestId('bulk-results')).toContainText('received', { timeout: 120_000 })
  // counts only: no score, status or outcome words anywhere on the page
  await expect(guest.locator('body')).not.toContainText(/score|recommend|approved|rejected|status/i)
  await guest.getByRole('button', { name: 'Send to the bank' }).click()
  await guest.getByRole('dialog').getByRole('button', { name: 'Yes, send' }).click()
  await expect(guest.getByText(/PRM-[0-9A-F]{8}/)).toBeVisible()
  await context.close()

  // the officer sees it as from the applicant, and can disable the link
  await page.getByRole('link', { name: 'Cases' }).first().click()
  await expect(page.getByText('From applicant').first()).toBeVisible()
  await expect(page.getByText('Applicant submitted').first()).toBeVisible()
  await page.getByRole('link', { name: 'Upload links' }).click()
  await page.getByRole('button', { name: 'Disable' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Yes, disable it' }).click()
  await expect(page.getByText('Disabled')).toBeVisible()

  // a disabled link is the same dead end as an unknown one
  const stale = await browser.newContext()
  const dead = await stale.newPage()
  await dead.goto(address)
  await expect(dead.getByRole('heading', { name: 'This link is not active' })).toBeVisible()
  await stale.close()
})
