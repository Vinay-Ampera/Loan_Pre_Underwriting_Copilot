import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

const rgb = (hex) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}
const LIGHT_BG = rgb('#f7f6fa')
const DARK_BG = rgb('#141220')

const bodyBg = (page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor)
const noSideScroll = (page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)

test('login is the landing page: brand panel, journey, score bar, no signup', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('list', { name: 'The five underwriting stages' })).toBeVisible()
  await expect(page.getByLabel('Score weights')).toContainText('Income and FOIR')
  await expect(page.getByText('A human confirms every case.')).toBeVisible()
  await expect(page.getByText('Pramaan is a sample bank. Synthetic data only.')).toBeVisible()
  await expect(page.getByRole('link', { name: /sign ?up|register/i })).toHaveCount(0)
  await expect(page).toHaveTitle('Pramaan')
})

test('system follows the OS, and dark and light override it', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/login')
  expect(await bodyBg(page)).toBe(DARK_BG) // system, OS dark
  await page.emulateMedia({ colorScheme: 'light' })
  expect(await bodyBg(page)).toBe(LIGHT_BG) // system, OS light

  await page.getByRole('radio', { name: 'Dark theme' }).click()
  expect(await bodyBg(page)).toBe(DARK_BG) // dark wins over an OS that is light
  await page.reload()
  expect(await bodyBg(page)).toBe(DARK_BG) // the choice is kept
  await page.getByRole('radio', { name: 'Light theme' }).click()
  await page.emulateMedia({ colorScheme: 'dark' })
  expect(await bodyBg(page)).toBe(LIGHT_BG) // light wins over an OS that is dark
  await page.getByRole('radio', { name: 'System theme' }).click()
  expect(await bodyBg(page)).toBe(DARK_BG)
})

test('no flash: the stored theme is on <html> before the app starts', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lc.theme', 'dark'))
  await page.goto('/login')
  const first = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
  expect(first).toBe('dark')
})

for (const [who, screens] of [
  ['officer', ['/', '/cases', '/cases/new']],
  ['admin', ['/', '/admin/precedents', '/admin/users']],
]) {
  for (const mode of ['light', 'dark']) {
    test(`${who} screens render in ${mode} mode without side scrolling`, async ({ page }) => {
      await page.addInitScript((m) => localStorage.setItem('lc.theme', m), mode)
      await signIn(page, who)
      await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
      for (const url of screens) {
        await page.goto(url)
        await expect(page.locator('main h1').first()).toBeVisible()
        expect(await bodyBg(page)).toBe(mode === 'dark' ? DARK_BG : LIGHT_BG)
        for (const size of [
          { width: 1280, height: 800 },
          { width: 900, height: 800 },
          { width: 390, height: 800 },
        ]) {
          await page.setViewportSize(size)
          expect(await noSideScroll(page), `${url} at ${size.width}px`).toBe(true)
        }
        await page.setViewportSize({ width: 1280, height: 800 })
      }
    })
  }
}

test('the sidebar shows icons only on a tablet width, with names kept for screen readers', async ({
  page,
}) => {
  await signIn(page, 'officer')
  await page.setViewportSize({ width: 900, height: 800 })
  const link = page.getByRole('link', { name: 'New case' }).first()
  await expect(link).toBeVisible()
  const width = await link.evaluate((el) => el.getBoundingClientRect().width)
  expect(width).toBeLessThan(60)
  await page.setViewportSize({ width: 1280, height: 800 })
  expect(await link.evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(120)
})

test('reduced motion switches off animation and the typing effect', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/login')
  const seconds = await page
    .locator('.login-card')
    .evaluate((el) => parseFloat(getComputedStyle(el).animationDuration))
  expect(seconds).toBeLessThan(0.01)
  const glow = await page
    .locator('.login-glow')
    .evaluate((el) => parseFloat(getComputedStyle(el).animationDuration))
  expect(glow).toBeLessThan(0.01)
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  const normal = await page
    .locator('.login-card')
    .evaluate((el) => parseFloat(getComputedStyle(el).animationDuration))
  expect(normal).toBeGreaterThan(0.1)
})

test('tiles open the case list filtered to that view', async ({ page }) => {
  await signIn(page, 'officer')
  await expect(page.getByLabel('Case summary')).toContainText('Awaiting confirmation')
  await page.getByRole('link', { name: /Stopped/ }).click()
  await expect(page).toHaveURL(/\/cases\?view=stopped/)
  await expect(page.getByText('Showing:')).toContainText('Stopped')
  await page.getByRole('button', { name: 'Show all cases' }).click()
  await expect(page.getByText('Showing:')).toHaveCount(0)
})
