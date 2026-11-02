// The theme choice is kept in the browser. Without one, the page follows the system setting
// (CSS, `prefers-color-scheme`). index.html runs the same logic before first paint.
export const THEME_KEY = 'lc.theme'
export const CHOICES = ['system', 'dark', 'light']

export function readTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY)
    return CHOICES.includes(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(choice, root = document.documentElement) {
  if (choice === 'dark' || choice === 'light') root.setAttribute('data-theme', choice)
  else root.removeAttribute('data-theme')
}

export function saveTheme(choice) {
  try {
    if (choice === 'system') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, choice)
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
}
