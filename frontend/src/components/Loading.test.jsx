import { act, render, screen, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { describe, expect, it } from 'vitest'
import { useAsync } from '../hooks/useAsync'
import { LoadingProvider, Reveal, useBooted } from './Loading'

const later = (value, ms) => new Promise((resolve) => setTimeout(() => resolve(value), ms))

function Slow({ ms, text }) {
  const { data } = useAsync(() => later(text, ms), [ms, text])
  return data ? <p>{data}</p> : null
}

const visible = (el) => !el.closest('.reveal-wait')

describe('Reveal', () => {
  it('keeps the screen hidden behind one loader until every request has finished', async () => {
    render(
      <Reveal>
        <h1>Home</h1>
        <Slow ms={20} text="fast part" />
        <Slow ms={250} text="slow part" />
      </Reveal>,
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(visible(screen.getByText('Home'))).toBe(false)
    await act(() => later(null, 120)) // the fast one is done, the slow one is not
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(visible(screen.getByText('fast part'))).toBe(false) // done, but not shown alone
    await waitFor(() => expect(visible(screen.getByText('slow part'))).toBe(true)) // all at once
    expect(visible(screen.getByText('fast part'))).toBe(true)
    expect(visible(screen.getByText('Home'))).toBe(true)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('waits for a request that only starts after another finished', async () => {
    function Chain() {
      const { data } = useAsync(() => later('one', 30), [])
      return data ? <Slow ms={60} text="two" /> : null
    }
    render(
      <Reveal>
        <Chain />
      </Reveal>,
    )
    await act(() => later(null, 60)) // the first is done; the second has just begun
    expect(screen.getByRole('status')).toBeInTheDocument()
    await waitFor(() => expect(visible(screen.getByText('two'))).toBe(true))
  })

  it('does not hide the screen again for a later load', async () => {
    function Later() {
      const [on, setOn] = useState(false)
      useEffect(() => {
        const t = setTimeout(() => setOn(true), 150)
        return () => clearTimeout(t)
      }, [])
      return on ? <Slow ms={100} text="late" /> : <p>Steady</p>
    }
    render(
      <Reveal>
        <Later />
      </Reveal>,
    )
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
    await act(() => later(null, 200)) // the later load starts now
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(visible(await screen.findByText('late'))).toBe(true)
  })

  it('tells the app it has started once the first screen is ready', async () => {
    function Probe() {
      return <span>{useBooted() ? 'booted' : 'booting'}</span>
    }
    render(
      <LoadingProvider>
        <Probe />
        <Reveal>
          <Slow ms={30} text="x" />
        </Reveal>
      </LoadingProvider>,
    )
    expect(screen.getByText('booting')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('booted')).toBeInTheDocument())
  })

  it('works without a Reveal around it, as in a page test', async () => {
    render(<Slow ms={10} text="plain" />)
    expect(await screen.findByText('plain')).toBeInTheDocument()
  })
})
