import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, readTheme, saveTheme, THEME_KEY } from './theme'

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('theme', () => {
  it('defaults to system and sets no attribute for it', () => {
    expect(readTheme()).toBe('system')
    applyTheme('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
  it('keeps a dark or light choice and applies it to <html>', () => {
    saveTheme('dark')
    expect(readTheme()).toBe('dark')
    applyTheme('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    saveTheme('light')
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
  })
  it('going back to system forgets the stored choice', () => {
    saveTheme('dark')
    saveTheme('system')
    expect(localStorage.getItem(THEME_KEY)).toBeNull()
    applyTheme('dark')
    applyTheme('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
  it('ignores a stored value it does not know and survives blocked storage', () => {
    localStorage.setItem(THEME_KEY, 'neon')
    expect(readTheme()).toBe('system')
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readTheme()).toBe('system')
    spy.mockRestore()
  })
})
