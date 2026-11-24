import { expect, test } from '@playwright/test'
import { PASSWORD, enterCode, signIn, signInAs } from './helpers'

const BASE = 'http://127.0.0.1:8765'

test('an admin sets up 2-step at the first sign-in, a recovery code works once, and another admin resets it', async ({
  page,
  browser,
}) => {
  // first sign-in: the password, then the setup screen with a QR code
  await signInAs(page, 'second@example.test', PASSWORD)
  await expect(page.getByRole('heading', { name: 'Set up 2-step verification' })).toBeVisible()
  await expect(page.getByText('Microsoft Authenticator', { exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: /QR code/ })).toBeVisible()
  await page.getByText('Cannot scan it? Type the key instead').click()
  const key = (await page.getByTestId('two-step-key').textContent()).replace(/\s/g, '')
  expect(key).toMatch(/^[A-Z2-7]{32}$/)

  // a wrong code is refused and the person stays on the step
  await page.getByLabel('6-digit code').fill('12345x')
  await page.getByRole('button', { name: 'Turn on and sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('That code is not right')
  await enterCode(page, key, 'Turn on and sign in')

  // the recovery codes are shown once; going on needs "I have saved these codes"
  await expect(page.getByRole('heading', { name: 'Save your recovery codes' })).toBeVisible()
  const codes = await page
    .getByRole('list', { name: 'Recovery codes' })
    .getByRole('listitem')
    .allTextContents()
  expect(codes).toHaveLength(8)
  const go = page.getByRole('button', { name: 'Continue to Pramaan' })
  await expect(go).toBeDisabled()
  await page.getByLabel('I have saved these codes').check()
  await go.click()
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()

  // lost phone: a recovery code signs in once
  const ctx2 = await browser.newContext({ baseURL: BASE })
  const p2 = await ctx2.newPage()
  await signInAs(p2, 'second@example.test', PASSWORD)
  await expect(p2.getByRole('heading', { name: 'Enter your code' })).toBeVisible()
  await expect(p2.getByRole('img', { name: /QR code/ })).toHaveCount(0) // no QR code again
  await p2.getByRole('button', { name: 'Lost your phone? Use a recovery code' }).click()
  await p2.getByLabel('Recovery code').fill(codes[0])
  await p2.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(p2.getByText('7 recovery codes')).toBeVisible()
  await p2.getByRole('button', { name: 'Continue to Pramaan' }).click()
  await expect(p2.getByRole('heading', { name: 'Home' })).toBeVisible()
  await ctx2.close()

  // the same recovery code is spent
  const ctx3 = await browser.newContext({ baseURL: BASE })
  const p3 = await ctx3.newPage()
  await signInAs(p3, 'second@example.test', PASSWORD)
  await p3.getByRole('button', { name: 'Lost your phone? Use a recovery code' }).click()
  await p3.getByLabel('Recovery code').fill(codes[0])
  await p3.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(p3.getByRole('alert')).toContainText('That code is not right')
  await ctx3.close()

  // the other admin (with their own code) resets it with a reason and a second click
  const ctx4 = await browser.newContext({ baseURL: BASE })
  const p4 = await ctx4.newPage()
  await signIn(p4, 'admin')
  await p4.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Users' }).click()
  const row = p4.getByRole('row', { name: /E2E Second Admin/ })
  await expect(row).toContainText('On')
  await expect(
    p4.getByRole('button', { name: 'Reset 2-step verification for E2E Admin' }),
  ).toBeDisabled() // not your own
  await row.getByRole('button', { name: 'Reset 2-step verification for E2E Second Admin' }).click()
  const confirm = p4.getByRole('button', { name: 'Yes, reset 2-step' })
  await expect(confirm).toBeDisabled()
  await p4.getByLabel('Why are you making this change?').fill('Lost the phone on the train')
  await confirm.click()
  await expect(row).toContainText('Set up at next sign-in')
  await ctx4.close()

  // the next sign-in shows a new QR code to scan
  const ctx5 = await browser.newContext({ baseURL: BASE })
  const p5 = await ctx5.newPage()
  await signInAs(p5, 'second@example.test', PASSWORD)
  await expect(p5.getByRole('heading', { name: 'Set up 2-step verification' })).toBeVisible()
  await ctx5.close()
})

test('an officer signs in with the password alone', async ({ page }) => {
  await signInAs(page, 'officer@example.test', PASSWORD)
  await expect(page.getByRole('heading', { name: 'Enter your code' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'New case' }).first()).toBeVisible()
})
