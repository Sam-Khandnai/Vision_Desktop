// @vitest-environment happy-dom
// Drives the real UI against the real backend (scripted fake model + real stdio MCP server).
import { afterAll, afterEach, beforeAll, expect, test } from 'vitest'
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
afterEach(cleanup) // every test starts from its own DOM, so the previous app cannot leak into the next

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

test('every message can be copied and a turn can be retried', async () => {
  localStorage.setItem('vision.lang', 'fa')
  const user = userEvent.setup()
  const calls = []
  // happy-dom has no clipboard API: stub it so the copy button has something to call
  const written = []
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: async (text) => { written.push(text) } },
  })
  const realFetch = globalThis.fetch
  globalThis.fetch = (url, opts) => { calls.push(String(url)); return realFetch(url, opts) }
  try {
    render(<App />)
    const box = await screen.findByPlaceholderText('پیامت را بنویس…', {}, { timeout: 15000 })
    await user.type(box, 'سلام')
    await user.click(screen.getByRole('button', { name: 'ارسال' }))
    expect(await screen.findByText('Hello there', {}, { timeout: 15000 })).toBeTruthy()

    // both the user message and the answer expose copy + retry
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'کپی' })).toHaveLength(2))
    expect(screen.getAllByRole('button', { name: 'تلاش دوباره' })).toHaveLength(2)

    await user.click(screen.getAllByRole('button', { name: 'کپی' })[1])
    expect(await screen.findByText('کپی شد')).toBeTruthy()

    expect(written[0].trim()).toBe('Hello there')
    await user.click(screen.getAllByRole('button', { name: 'کپی' })[0])
    await waitFor(() => expect(written[1]).toBe('سلام'))

    // retrying the answer re-runs the turn for the same user message
    calls.length = 0
    await user.click(screen.getAllByRole('button', { name: 'تلاش دوباره' })[1])
    await waitFor(() => expect(calls.some((u) => u.endsWith('/retry'))).toBe(true), { timeout: 15000 })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'توقف' })).toBeNull(), { timeout: 15000 })
    expect(document.querySelectorAll('.thread .msg.user')).toHaveLength(1) // the user message was not duplicated
    expect(document.querySelectorAll('.thread .msg.assistant')).toHaveLength(1)
  } finally {
    globalThis.fetch = realFetch
  }
}, 120000)

test('a local Ollama model can be added without an API key', async () => {
  localStorage.setItem('vision.lang', 'fa')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: 'تنظیمات' }, { timeout: 15000 }))
  const tabs = await screen.findAllByRole('tab')
  await user.click(tabs[1]) // Model & API

  await user.click(await screen.findByRole('button', { name: 'افزودن مدل' }))
  await user.click(screen.getByRole('button', { name: 'Ollama' }))

  // local mode hides the API key field and pre-fills the Ollama address
  const localSwitch = screen.getByRole('switch', { name: 'مدل محلی (Ollama)' })
  expect(localSwitch.getAttribute('aria-checked')).toBe('true')
  expect(screen.queryByLabelText('کلید API')).toBeNull()
  expect(screen.getByDisplayValue('http://localhost:11434/v1')).toBeTruthy()

  await user.type(screen.getByPlaceholderText('provider-model-id'), 'llama3')
  await user.click(screen.getByRole('button', { name: 'ذخیره' }))

  // the saved provider is listed with the local badge
  expect(await screen.findByText('محلی', {}, { timeout: 10000 })).toBeTruthy()
  expect(screen.getByText(/llama3/)).toBeTruthy()
}, 120000)

// The model switcher in the chat lists every model of every provider and remembers the choice.
test('the chat model picker switches the answering model', async () => {
  localStorage.setItem('vision.lang', 'en')
  localStorage.removeItem('vision.model')
  const user = userEvent.setup()
  render(<App />)

  const picker = await screen.findByRole('button', { name: /Choose a model|fake-1/i }, { timeout: 15000 })
  // the picker sits inside the message box, not in a separate bar above it
  expect(picker.closest('.composer')).toBeTruthy()
  await user.click(picker)
  const list = await screen.findByRole('listbox', { name: 'Choose a model' })
  await user.click(await within(list).findByRole('option', { name: /fake-1/ }, { timeout: 15000 }))
  expect(screen.getByRole('button', { name: /fake-1/i })).toBeTruthy()
  expect(JSON.parse(localStorage.getItem('vision.model')).model_name).toBe('fake-1')
}, 120000)
