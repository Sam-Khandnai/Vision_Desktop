// @vitest-environment happy-dom
// Drives the real UI against the real backend (scripted fake model + real stdio MCP server).
import { afterAll, beforeAll, expect, test } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { spawn } from 'node:child_process'
import App from './App.jsx'

let proc
beforeAll(async () => {
  const port = process.env.SMOKE_PORT || '8791'
  proc = spawn('uv', ['run', 'python', 'tests/serve_fake.py', port], { cwd: '..', stdio: ['ignore', 'pipe', 'inherit'] })
  await new Promise((resolve, reject) => {
    proc.stdout.on('data', (d) => String(d).includes('READY') && resolve())
    proc.on('exit', () => reject(new Error('backend exited')))
    setTimeout(() => reject(new Error('backend timeout')), 60000)
  })
  await new Promise((r) => setTimeout(r, 2500)) // let the MCP server connect
}, 90000)
afterAll(() => { cleanup(); proc?.kill() })

test('chat, tool approval, settings and catalog work end to end', async () => {
  localStorage.setItem('vision.lang', 'fa')
  const user = userEvent.setup()
  render(<App />)

  // empty state in Persian, provider already configured so no banner
  expect(await screen.findByText('امروز چه کاری داریم؟', {}, { timeout: 15000 })).toBeTruthy()
  expect(screen.queryByText('برای شروع، یک مدل (Provider) متصل کن.')).toBeNull()

  const box = screen.getByPlaceholderText('پیامت را بنویس…')
  await user.type(box, 'سلام')
  await user.click(screen.getByRole('button', { name: 'ارسال' }))
  expect(await screen.findByText('Hello there', {}, { timeout: 15000 })).toBeTruthy()
  // history shows the new conversation, titled from the first message
  await waitFor(() => expect(within(screen.getByRole('navigation')).getByText('سلام')).toBeTruthy())

  // read-only MCP tool: runs without asking, card + final answer appear
  await user.type(box, 'please use echo')
  await user.click(screen.getByRole('button', { name: 'ارسال' }))
  expect(await screen.findByText(/Tool said:.*echo:hi/, {}, { timeout: 20000 })).toBeTruthy()

  // changing tool: waits for approval, then runs after "Allow"
  await user.type(box, 'please use delete')
  await user.click(screen.getByRole('button', { name: 'ارسال' }))
  const allow = await screen.findByRole('button', { name: 'اجازه بده' }, { timeout: 20000 })
  await user.click(allow)
  expect(await screen.findByText(/Tool said:.*deleted:x/, {}, { timeout: 20000 })).toBeTruthy()

  // settings: three tabs, MCP tab lists the server and links to the catalog
  await user.click(screen.getByRole('button', { name: 'تنظیمات' }))
  const tabs = await screen.findAllByRole('tab')
  expect(tabs.map((t) => t.textContent)).toEqual(['حساب', 'مدل و API', 'MCP'])
  await user.click(tabs[2])
  expect(await screen.findByText('fake')).toBeTruthy()
  await user.click(screen.getByText('مرور کاتالوگ MCP'))

  // catalog page: 50+ servers, search narrows, install dialog asks for the needed info
  expect(await screen.findByText('Filesystem', {}, { timeout: 10000 })).toBeTruthy()
  const count = Number(screen.getByText(/\d+ سرور آماده/).textContent.match(/(\d+)/)[1])
  expect(count).toBeGreaterThanOrEqual(90)
  // catalog texts are Persian now
  expect(screen.getByText('خواندن، جستجو و ویرایش فایل‌ها در یک پوشه‌ی مشخص.')).toBeTruthy()
  await user.type(screen.getByPlaceholderText('جستجوی ابزار…'), 'github')
  await waitFor(() => expect(screen.queryByText('Filesystem')).toBeNull())
  const card = screen.getByText('GitHub').closest('article')
  await user.click(within(card).getByRole('button', { name: 'افزودن' }))
  expect(await screen.findByText('توکن شخصی GitHub (PAT)')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: 'انصراف' }))

  // switch the whole UI to English with the sidebar toggle: UI strings AND catalog texts change
  await user.click(screen.getByRole('button', { name: 'English' }))
  expect(await screen.findByRole('heading', { name: 'MCP catalog' })).toBeTruthy()
  await user.clear(screen.getByPlaceholderText('Search tools…'))
  await user.type(screen.getByPlaceholderText('Search tools…'), 'github')
  const ghCard = (await screen.findByText('GitHub')).closest('article')
  expect(within(ghCard).getByText('Work with repos, issues and pull requests on GitHub.')).toBeTruthy()
  await user.click(within(ghCard).getByRole('button', { name: 'Add' }))
  expect(await screen.findByText('GitHub personal access token (PAT)')).toBeTruthy()
  // searching in the other language still finds it (search covers both languages)
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.clear(screen.getByPlaceholderText('Search tools…'))
  await user.type(screen.getByPlaceholderText('Search tools…'), 'مخزن')
  expect(await screen.findByText('GitHub')).toBeTruthy()
  expect(localStorage.getItem('vision.lang')).toBe('en')
}, 120000)
