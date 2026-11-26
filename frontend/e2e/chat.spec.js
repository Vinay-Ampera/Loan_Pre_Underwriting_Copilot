import { expect, test } from '@playwright/test'
import { cleanCase, createCase, signIn, uploadAll } from './helpers'

/** The admin's real model switch (AI control, Settings), with its reason and second click. */
async function setModels(browser, on) {
  const page = await browser.newPage()
  await signIn(page, 'admin')
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  await page.goto('/admin/ai')
  await page.getByRole('tab', { name: /^Settings/ }).click()
  await page.getByRole('checkbox', { name: /Models are on/ }).setChecked(on)
  await page.getByRole('button', { name: 'Review and save' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox').fill('Browser test of the chat switch.')
  await dialog.getByRole('button', { name: 'Yes, save' }).click()
  await expect(page.getByText(/^Saved as version/)).toBeVisible()
  await page.close()
}

// "Ask this case" (Stage 12 Part E): the test server answers the chat from a script that cites
// what it was really given (backend/tests/e2e_server.py).
test('an officer asks about a case, sees a cited answer and opens the clause', async ({
  page,
  browser,
}) => {
  const caseId = cleanCase('PL')
  await signIn(page, 'officer')
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  const url = await createCase(page, caseId, 'Personal loan')

  await page.getByRole('tab', { name: 'Ask this case' }).click()
  await expect(page.getByText('Chat opens when the report is ready.')).toBeVisible()
  await page.getByRole('tab', { name: 'Documents' }).click()
  await uploadAll(page, caseId)
  await page.getByRole('button', { name: 'Submit for assessment' }).click()
  await expect(page.getByText('Awaiting confirmation').first()).toBeVisible({ timeout: 240_000 })

  await page.getByRole('tab', { name: 'Ask this case' }).click()
  await expect(page.getByText(/Chat cannot change the score or decide anything/)).toBeVisible()
  const box = page.getByLabel('Your question')
  await box.fill('Why did Income and FOIR lose points?')
  await box.press('Enter')
  await expect(page.getByText('The case records a result for this check.')).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.getByText('Check the cited source before relying on an answer.')).toBeVisible()
  await expect(page.getByText(/Payslip · employer/)).toBeVisible()
  const chip = page.locator('.chat-clause-chip').first()
  await chip.click()
  await expect(page.locator('.chat-clause')).toBeVisible()

  // a what-if is answered by code with a pointer to the counter-offer box
  await box.fill('What if the amount were 5 lakh?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText(/does not work out other amounts or tenures/)).toBeVisible()
  // nothing about the case moved: it still waits for the officer
  await expect(page.getByRole('button', { name: 'Confirm recommendation' })).toBeVisible()

  await setModels(browser, false)
  try {
    await page.goto(url)
    await page.getByRole('tab', { name: 'Ask this case' }).click()
    await expect(page.getByText(/^Chat is off because the AI models/)).toBeVisible()
    await expect(page.getByLabel('Your question')).toBeDisabled()
    // the earlier turns are still there after coming back
    await expect(page.getByText('The case records a result for this check.')).toBeVisible()
  } finally {
    await setModels(browser, true)
  }
})
