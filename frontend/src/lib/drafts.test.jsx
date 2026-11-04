import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { clearDrafts, useDraft } from './drafts'

const signIn = (id) =>
  sessionStorage.setItem('lc.session', JSON.stringify({ token: 't', user: { id } }))

describe('useDraft', () => {
  it('restores what was typed after the page is rebuilt', () => {
    signIn('u1')
    const first = renderHook(() => useDraft('reason'))
    act(() => first.result.current[1]('Salary checked with the employer'))
    first.unmount()
    const again = renderHook(() => useDraft('reason'))
    expect(again.result.current[0]).toBe('Salary checked with the employer')
  })

  it("does not show one person's draft to another", () => {
    signIn('u1')
    const mine = renderHook(() => useDraft('reason'))
    act(() => mine.result.current[1]('private words'))
    signIn('u2')
    expect(renderHook(() => useDraft('reason')).result.current[0]).toBe('')
  })

  it('is gone after discard, and after a deliberate sign-out wipes drafts', () => {
    signIn('u1')
    const a = renderHook(() => useDraft('reason'))
    act(() => a.result.current[1]('text'))
    act(() => a.result.current[2]())
    expect(renderHook(() => useDraft('reason')).result.current[0]).toBe('')
    const b = renderHook(() => useDraft('other'))
    act(() => b.result.current[1]('more'))
    clearDrafts()
    expect(renderHook(() => useDraft('other')).result.current[0]).toBe('')
  })
})
