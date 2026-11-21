import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

const OLD = 'Annual turnover must be at least Rs 36 lakh'
const NEW =
  'Annual turnover must be at least Rs 40 lakh, as shown in GST returns and income tax returns.'

test('the admin changes one clause, checks and publishes it, and an officer reads the new text', async ({
  page,
  browser,
}) => {
  await signIn(page, 'admin')
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Knowledge base' })
    .click()
  await expect(page.getByRole('heading', { name: 'Knowledge base' })).toBeVisible()
  await page.getByRole('button', { name: /Business loan/ }).click()
  await expect(page.getByText(OLD)).toBeVisible()
  await expect(page.getByText(/BL-INC-11/)).toBeVisible() // the rule that reads this clause

  await page.getByRole('tab', { name: 'Change' }).click()
  await page.getByRole('button', { name: 'Change BL-ELIG-04' }).click()
  await page.getByLabel('Clause text').fill(NEW)
  await page.getByRole('button', { name: 'Save to the draft' }).click()

  // the rules file still says 36 lakh: the check warns, publishing waits for the retrieval check
  await expect(page.getByText(/no longer mentions it/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Publish…' })).toBeDisabled()
  await page.getByRole('button', { name: 'Run the retrieval check' }).click()
  await expect(page.getByRole('table', { name: /Search quality/ })).toBeVisible()
  await page.getByRole('button', { name: 'Publish…' }).click()
  const dialog = page.getByRole('dialog')
  await dialog
    .getByLabel('Why are you making this change?')
    .fill('Yearly update of the turnover floor')
  await expect(dialog.getByRole('button', { name: 'Yes, publish' })).toBeDisabled()
  await dialog.getByLabel(/I have read the/).check()
  await dialog.getByRole('button', { name: 'Yes, publish' }).click()
  await expect(page.getByText('There is no draft.')).toBeVisible()

  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page.getByText('Yearly update of the turnover floor')).toBeVisible()

  const officer = await (await browser.newContext()).newPage()
  await signIn(officer, 'officer')
  await officer
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Policies' })
    .click()
  await officer.getByRole('button', { name: /Business loan/ }).click()
  await expect(officer.getByText('Annual turnover must be at least Rs 40 lakh')).toBeVisible()
  await expect(officer.getByRole('tab', { name: 'Change' })).toHaveCount(0)
})
