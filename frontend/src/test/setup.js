import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'

// Saved drafts and the session live in sessionStorage; start every test from a clean slate.
afterEach(() => {
  sessionStorage.clear()
  localStorage.clear()
})
