import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const css = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), 'tokens.css'),
  'utf8',
)

function declarations(block) {
  const out = {}
  for (const m of block.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}
function blockAfter(selector) {
  const start = css.indexOf(selector)
  if (start < 0) throw new Error(`no block for ${selector}`)
  const open = css.indexOf('{', start)
  let depth = 0
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++
    if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i)
  }
  throw new Error('unbalanced')
}

const light = declarations(blockAfter(':root {'))
const darkOnly = declarations(blockAfter(":root[data-theme='dark'] {"))
const dark = { ...light, ...darkOnly }
const system = declarations(blockAfter(':root:not([data-theme]) {'))

const resolve = (theme, value, depth = 0) => {
  const m = /^var\((--[\w-]+)\)$/.exec(value)
  return m && depth < 5 ? resolve(theme, theme[m[1]], depth + 1) : value
}
function luminance(hex) {
  const n = parseInt(hex.slice(1), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// [foreground, background]: every text pairing used by the components, checked for AA (4.5:1).
const PAIRS = [
  ['--ink', '--bg'],
  ['--ink', '--surface'],
  ['--muted', '--bg'],
  ['--muted', '--surface'],
  ['--muted', '--stopped-bg'],
  ['--primary', '--surface'],
  ['--primary', '--bg'],
  ['--primary', '--brand-soft'],
  ['--primary-ink', '--primary'],
  ['--primary-ink', '--primary-hover'],
  ['--approve', '--approve-bg'],
  ['--refer', '--refer-bg'],
  ['--reject', '--reject-bg'],
  ['--stopped', '--stopped-bg'],
  ['--unverified', '--unverified-bg'],
  ['--approve', '--surface'],
  ['--reject', '--surface'],
  ['--reject', '--bg'],
  ['--danger-ink', '--danger-bg'],
  ['--danger-ink', '--danger-hover'],
  ['--ink', '--brand-soft'],
]

describe.each([
  ['light', light],
  ['dark', dark],
])('%s theme', (_name, theme) => {
  it.each(PAIRS)('%s on %s passes WCAG AA (4.5:1)', (fg, bg) => {
    const ratio = contrast(resolve(theme, theme[fg]), resolve(theme, theme[bg]))
    expect(ratio, `${fg} on ${bg} = ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
  })

  it('has the planned brand tokens', () => {
    expect(theme['--brand']).toBeDefined()
    expect(theme['--brand-strong']).toBeDefined()
    expect(theme['--brand-soft']).toBeDefined()
  })
})

describe('tokens', () => {
  it('uses the planned button purple in the light theme', () => {
    expect(light['--brand-strong']).toBe('#5e4fa0')
    expect(light['--brand']).toBe('#7c70af')
  })

  it('the white panel text passes AA on the whole login gradient', () => {
    const stops = light['--panel-bg'].match(/#[0-9a-f]{6}/gi)
    expect(stops.length).toBeGreaterThan(1)
    for (const s of stops) expect(contrast('#ffffff', s)).toBeGreaterThanOrEqual(4.5)
  })

  it('system dark and explicit dark define the same values', () => {
    expect(system).toEqual(darkOnly)
  })

  it('keeps unverified off the brand purple', () => {
    for (const t of [light, dark]) {
      expect(t['--unverified']).not.toBe(t['--brand'])
      expect(t['--unverified']).not.toBe(t['--brand-strong'])
    }
  })
})
