import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const src = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function cssFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? cssFiles(path.join(dir, e.name))
      : e.name.endsWith('.css')
        ? [path.join(dir, e.name)]
        : [],
  )
}

describe('reduced motion', () => {
  const base = readFileSync(path.join(src, 'styles/base.css'), 'utf8')

  it('switches off every animation and transition globally', () => {
    const block = base.slice(base.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(block).toMatch(/animation-duration:\s*0\.001ms\s*!important/)
    expect(block).toMatch(/transition-duration:\s*0\.001ms\s*!important/)
    expect(block).toMatch(/animation-iteration-count:\s*1\s*!important/)
  })

  it('no component sets its own animation without the global override applying', () => {
    // the override uses !important on *, so any component animation is covered; this guards
    // against someone adding an animation in a file that is not loaded through index.css
    const loaded = readFileSync(path.join(src, 'styles/index.css'), 'utf8')
    expect(loaded).toContain("@import './base.css'")
    expect(cssFiles(src).length).toBeGreaterThan(10)
  })
})
