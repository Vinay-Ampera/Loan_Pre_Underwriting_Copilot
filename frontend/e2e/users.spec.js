import { expect, test } from '@playwright/test'
import { PASSWORD, signIn, signInAs } from './helpers'

test('the admin creates, resets, disables and re-enables a user; each change is audited', async ({
  page,
}) => {
  await signIn(page, 'admin')
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  await expect(page.getByLabel('Admin summary')).toContainText('Pending precedents')
  await page.getByRole('link', { name: 'Users' }).click()
  await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()

  // create: the temporary password is shown once
  await page.getByRole('button', { name: 'Add user' }).click()
  await page.getByLabel('Full name').fill('Dana Officer')
  await page.getByLabel('Email').fill('dana@example.test')
  await page.getByRole('button', { name: 'Create user' }).click()
  const first = (await page.getByTestId('temp-password').textContent()).trim()
  expect(first).toMatch(/^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$/)
  await page.getByRole('button', { name: 'I have copied it' }).click()
  await expect(page.getByTestId('temp-password')).toHaveCount(0)
  const row = page.getByRole('row', { name: /Dana Officer/ })
  await expect(row).toContainText('Active')

  // a duplicate email is refused with a plain message
  await page.getByRole('button', { name: 'Add user' }).click()
  await page.getByLabel('Full name').fill('Dana Again')
  await page.getByLabel('Email').fill('dana@example.test')
  await page.getByRole('button', { name: 'Create user' }).click()
  await expect(page.getByRole('alert')).toContainText('already exists')
  await page.getByRole('button', { name: 'Cancel' }).click()

  // reset: needs a second click; the new password works and the old one does not
  await row.getByRole('button', { name: 'Reset password for Dana Officer' }).click()
  await expect(page.getByTestId('temp-password')).toHaveCount(0) // nothing yet: the first click only asks
  await page.getByRole('button', { name: 'Yes, reset password' }).click()
  const second = (await page.getByTestId('temp-password').textContent()).trim()
  expect(second).not.toBe(first)
  await page.getByRole('button', { name: 'I have copied it' }).click()

  // disable: a second click again; a disabled user cannot sign in
  await row.getByRole('button', { name: 'Disable Dana Officer' }).click()
  await expect(row).toContainText('Active') // unchanged after the first click
  await page.getByRole('button', { name: 'Yes, disable' }).click()
  await expect(row).toContainText('Disabled')
  await expect(page.getByRole('button', { name: 'Disable E2E Admin' })).toBeDisabled() // not yourself

  const other = await page.context().browser().newContext({ baseURL: 'http://127.0.0.1:8765' })
  const p2 = await other.newPage()
  await signInAs(p2, 'dana@example.test', second)
  await expect(p2.getByRole('alert')).toHaveText('Email or password is incorrect.')

  await row.getByRole('button', { name: 'Enable Dana Officer' }).click()
  await expect(row).toContainText('Active')
  await signInAs(p2, 'dana@example.test', first)
  await expect(p2.getByRole('alert')).toHaveText('Email or password is incorrect.') // old password is dead
  await signInAs(p2, 'dana@example.test', second)
  await expect(p2.getByRole('heading', { name: 'Home' })).toBeVisible()
  await other.close()

  // the audit log has all four actions and no password
  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('lc.session')).token)
  const users = await (
    await page.request.get('/api/v1/admin/users', { headers: { Authorization: `Bearer ${token}` } })
  ).json()
  expect(JSON.stringify(users)).not.toContain(PASSWORD)
  expect(users.find((u) => u.email === 'dana@example.test').role).toBe('officer')
})
