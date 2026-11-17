// Guards the craft pass (docs/DESIGN_SYSTEM.md section 8.11): no hue gradients, glows, upper-case
// tracked labels, heavy weights, catch-all transitions, hover lifts or text glyphs used as icons.
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const src = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function files(dir, ext) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return files(p, ext)
    return e.name.endsWith(ext) && !e.name.includes('.test.') ? [p] : []
  })
}
const css = files(src, '.css').map((f) => [path.relative(src, f), readFileSync(f, 'utf8')])
const jsx = files(src, '.jsx').map((f) => [path.relative(src, f), readFileSync(f, 'utf8')])

// Only states that are really live may loop: a case being assessed, the stage in progress, and
// a loading placeholder.
const LOOP_OK = [
  'components/StatusChip.css',
  'components/StageProgress.css',
  'components/States.css',
]

describe('craft rules for every stylesheet', () => {
  it.each(css)('%s has no gradients, glows or catch-all transitions', (_name, text) => {
    expect(text).not.toMatch(/(linear|radial|conic)-gradient\(/)
    expect(text).not.toMatch(/transition:\s*all/)
    expect(text).not.toMatch(/drop-shadow\(/)
  })

  it.each(css)('%s uses sentence case and weights 400 to 600', (_name, text) => {
    expect(text).not.toMatch(/text-transform:\s*uppercase/)
    for (const m of text.matchAll(/font-weight:\s*(\d+)/g))
      expect(Number(m[1])).toBeLessThanOrEqual(600)
    expect(text).not.toMatch(/font-weight:\s*bold/)
  })

  it.each(css)('%s does not lift or scale things on hover', (_name, text) => {
    for (const m of text.matchAll(/:hover[^{]*\{([^}]*)\}/g)) expect(m[1]).not.toMatch(/transform/)
  })

  it.each(css)('%s loops an animation only for a live state', (name, text) => {
    if (LOOP_OK.includes(name)) return
    expect(text).not.toMatch(/infinite/)
  })
})

describe('icons', () => {
  it.each(jsx)('%s draws status marks with line icons, not text glyphs', (_name, text) => {
    expect(text).not.toMatch(/[✓✕⟳○●■✨🚀]/u)
  })
})
