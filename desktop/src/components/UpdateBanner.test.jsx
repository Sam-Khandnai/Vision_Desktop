// @vitest-environment happy-dom
import { expect, test, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppCtx } from '../ctx'
import { makeT } from '../i18n'
import UpdateBanner from './UpdateBanner'

test('banner follows downloading -> ready and restarts the app on click', async () => {
  let push = () => {}
  const install = vi.fn()
  window.vision = {
    getUpdate: () => Promise.resolve(null),
    onUpdate: (cb) => { push = cb; return () => {} },
    installUpdate: install,
  }
  render(<AppCtx.Provider value={{ t: makeT('en') }}><UpdateBanner /></AppCtx.Provider>)
  expect(screen.queryByRole('status')).toBeNull()

  await act(async () => push({ state: 'downloading', version: '0.2.0', percent: 40 }))
  expect(screen.getByText(/Downloading version 0\.2\.0/)).toBeTruthy()
  expect(screen.queryByRole('button')).toBeNull()

  await act(async () => push({ state: 'ready', version: '0.2.0' }))
  expect(screen.getByText(/Version 0\.2\.0 is ready/)).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: /Restart and update/ }))
  expect(install).toHaveBeenCalledTimes(1)
})
