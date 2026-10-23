// @vitest-environment happy-dom
import { afterEach, expect, test } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { AppCtx } from '../ctx'
import { makeT } from '../i18n'
import { ActivityStrip } from './Chat'

const renderStrip = (lang, toolName) =>
  render(<AppCtx.Provider value={{ t: makeT(lang) }}><ActivityStrip toolName={toolName} /></AppCtx.Provider>)

afterEach(cleanup)

test('shows the thinking state while no tool is running', () => {
  renderStrip('en')
  const status = screen.getByRole('status')
  expect(status.textContent).toContain('Thinking')
  expect(status.className).toContain('activity')
  expect(status.querySelector('.activity-orb')).toBeTruthy()
  expect(status.querySelectorAll('.activity-dots b')).toHaveLength(3)
})

test('names the tool that is being called', () => {
  renderStrip('en', 'filesystem')
  expect(screen.getByRole('status').textContent).toContain('Calling filesystem')
})

test('is translated to Persian', () => {
  renderStrip('fa')
  expect(screen.getByRole('status').textContent).toContain('در حال فکر کردن')
})
