import { expect, test } from '@playwright/test'
import { cleanCase, createCase, signIn, uploadAll } from './helpers'

const LOANS = [
  ['PL', 'Personal loan'],
  ['HL', 'Home loan'],
  ['ED', 'Education loan'],
  ['BL', 'Business loan'],
  ['VL', 'Vehicle loan'],
]

// One case per loan type, end to end in the browser: create, upload, submit, wait for the
// assessment, read the report, export the PDF, then confirm with the second click.
for (const [prefix, label] of LOANS) {
  test(`${label}: from new case to a confirmed recommendation`, async ({ page }) => {
    const caseId = cleanCase(prefix)
    await signIn(page, 'officer')
    await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
    await createCase(page, caseId, label)

    // submit is blocked until the KYC documents are in
    await expect(page.getByRole('button', { name: 'Submit for assessment' })).toBeDisabled()
    await uploadAll(page, caseId)
    const submit = page.getByRole('button', { name: 'Submit for assessment' })
    await expect(submit).toBeEnabled()
    await submit.click()

    // progress by stage, then the pause for the officer
    await expect(page.getByRole('list', { name: 'Assessment progress' })).toBeVisible()
    await expect(page.getByText('Awaiting confirmation').first()).toBeVisible({ timeout: 240_000 })
    await page.getByRole('tab', { name: 'Report' }).click()
    await expect(page.getByRole('heading', { name: /^Recommended:/ })).toBeVisible()
    await expect(page.getByText('Awaiting your confirmation.').first()).toBeVisible()
    await expect(page.getByRole('button', { name: /^KYC/ })).toBeVisible()
    await expect(page.locator('body')).not.toContainText(/\b(is|was|been)\s+approved\b/i)

    // extracted fields beside the document
    await page.getByRole('tab', { name: 'Extracted fields' }).click()
    await page.getByLabel('Document').selectOption({ index: 1 })
    await expect(page.locator('.viewer .fields')).toBeVisible()
    await page.getByRole('tab', { name: 'Report' }).click()

    // PDF export
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export PDF' }).click()
    expect((await download).suggestedFilename()).toMatch(/^CASE-\d{4}-\d{4}-report\.pdf$/)

    // the first click only opens the dialog; the second records the decision
    await page.getByRole('button', { name: 'Confirm recommendation' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(page.getByText('Awaiting confirmation').first()).toBeVisible()
    await dialog.getByRole('button', { name: 'Yes, confirm' }).click()
    await expect(page.getByText('Recommendation confirmed')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Confirm recommendation' })).toHaveCount(0)

    // the audit tab shows who did what
    await page.getByRole('tab', { name: 'Audit' }).click()
    await expect(page.getByText('Recommendation confirmed').first()).toBeVisible()
    await expect(page.getByText('Submitted for assessment')).toBeVisible()
  })
}

test('override is blocked without a reason and needs the second click', async ({ page }) => {
  const caseId = cleanCase('PL')
  await signIn(page, 'officer')
  await createCase(page, caseId, 'Personal loan')
  await uploadAll(page, caseId)
  await page.getByRole('button', { name: 'Submit for assessment' }).click()
  await expect(page.getByText('Awaiting confirmation').first()).toBeVisible({ timeout: 240_000 })

  await page.getByRole('button', { name: 'Override' }).click()
  const dialog = page.getByRole('dialog')
  const submit = dialog.getByRole('button', { name: 'Submit override' })
  await expect(submit).toBeDisabled()
  await dialog.getByLabel('Your decision').selectOption('refer')
  await expect(submit).toBeDisabled() // a decision without a reason is still blocked
  await dialog.getByLabel('Reason (required)').fill('too short')
  await expect(submit).toBeDisabled()
  await dialog
    .getByLabel('Reason (required)')
    .fill('Income verified in person at the branch visit.')
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText('Recommendation overridden')).toBeVisible()
  await expect(page.getByText('Income verified in person at the branch visit.')).toBeVisible()
})
