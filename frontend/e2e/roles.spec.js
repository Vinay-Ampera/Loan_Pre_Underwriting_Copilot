import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('an admin has no way to create or upload, and an officer has no precedent queue', async ({
  page,
}) => {
  await signIn(page, 'admin')
  await expect(page).toHaveURL(/\/admin\/precedents/)
  await expect(page.getByRole('link', { name: 'New case' })).toHaveCount(0)
  await page.goto('/cases/new') // typing the address does not help: the route is for officers
  await expect(page).toHaveURL(/\/admin\/precedents/)

  // and the server refuses even when the UI is bypassed
  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('lc.session')).token)
  const headers = { Authorization: `Bearer ${token}` }
  expect((await page.request.get('/api/v1/cases', { headers })).status()).toBe(403)
  const upload = await page.request.post(
    '/api/v1/cases/00000000-0000-0000-0000-000000000000/documents',
    {
      headers,
      multipart: {
        role: 'primary',
        files: { name: 'a.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') },
      },
    },
  )
  expect(upload.status()).toBe(403)
})

test('an officer cannot open or call the precedent queue', async ({ page }) => {
  await signIn(page, 'officer')
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Precedent queue' })).toHaveCount(0)
  await page.goto('/admin/precedents')
  await expect(page).not.toHaveURL(/admin/)
  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('lc.session')).token)
  const headers = { Authorization: `Bearer ${token}` }
  expect((await page.request.get('/api/v1/admin/precedents', { headers })).status()).toBe(403)
  const id = '00000000-0000-0000-0000-000000000000'
  expect(
    (
      await page.request.post(`/api/v1/admin/precedents/${id}/approve`, { headers, data: {} })
    ).status(),
  ).toBe(403)
})

test('the admin reviews a precedent: approve needs a dialog and an expiry date', async ({
  page,
}) => {
  await signIn(page, 'admin')
  const card = page.locator('article', { hasText: 'CASE-2026-9001' })
  await expect(card).toContainText('Stable employer for ten years')
  await card.getByRole('button', { name: 'Approve…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Valid until')).not.toHaveValue('')
  await expect(card).toContainText('pending') // nothing changed after the first click
  await dialog.getByRole('button', { name: 'Yes, approve precedent' }).click()
  await expect(dialog).toHaveCount(0) // the approval went through and the dialog closed
  await page.getByRole('tab', { name: 'Approved' }).click()
  await expect(page.locator('article', { hasText: 'CASE-2026-9001' })).toContainText('Approved by')
})

test('wrong password shows one plain message', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('officer@example.test')
  await page.getByLabel('Password').fill('not the password')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toHaveText('Email or password is incorrect.')
})
