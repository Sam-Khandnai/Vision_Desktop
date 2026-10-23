let cfg = { baseUrl: 'http://127.0.0.1:8765', token: '' }

export async function initApi() {
  if (window.vision) cfg = await window.vision.getBackend()
  else if (import.meta.env.VITE_BACKEND) cfg = { baseUrl: import.meta.env.VITE_BACKEND, token: '' }
}

const headers = (json = true) => ({
  ...(json ? { 'Content-Type': 'application/json' } : {}),
  ...(cfg.token ? { Authorization: `Bearer ${cfg.token}` } : {}),
})

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function toError(res) {
  let detail = res.statusText
  try {
    const data = await res.json()
    detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
  } catch (_) {}
  return new ApiError(detail, res.status)
}

async function req(method, path, body) {
  let res
  try {
    res = await fetch(cfg.baseUrl + path, { method, headers: headers(), body: body === undefined ? undefined : JSON.stringify(body) })
  } catch (e) {
    throw new ApiError('offline', 0)
  }
  if (!res.ok) throw await toError(res)
  return res.json()
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b = {}) => req('POST', p, b),
  put: (p, b) => req('PUT', p, b),
  patch: (p, b) => req('PATCH', p, b),
  del: (p) => req('DELETE', p),
}

// Server-sent events over fetch (EventSource cannot send POST bodies or auth headers).
async function streamEvents(path, body, onEvent, signal) {
  let res
  try {
    res = await fetch(cfg.baseUrl + path, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e // the user pressed Stop
    throw new ApiError('offline', 0) // an unreachable engine must not surface as "Failed to fetch"
  }
  if (!res.ok) throw await toError(res)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const line = block.split('\n').find((l) => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)))
    }
  }
}

export const streamChat = (conversationId, message, onEvent, signal) =>
  streamEvents(`/api/conversations/${conversationId}/chat`, { message }, onEvent, signal)

export const streamChatWithModel = (conversationId, message, model, onEvent, signal) =>
  streamEvents(`/api/conversations/${conversationId}/chat`,
    { message, provider_id: model?.provider_id, model_name: model?.model_name }, onEvent, signal)

export const streamRetry = (conversationId, messageId, onEvent, signal) =>
  streamEvents(`/api/conversations/${conversationId}/retry`, { message_id: messageId }, onEvent, signal)

export const openExternal = (url) => (window.vision ? window.vision.openExternal(url) : window.open(url, '_blank'))
export const pickFolder = () => (window.vision ? window.vision.pickFolder() : Promise.resolve(null))
export const pickFile = () => (window.vision ? window.vision.pickFile() : Promise.resolve(null))
export const hasNativePicker = () => Boolean(window.vision)

// navigator.clipboard needs a secure context; fall back to a hidden textarea so copy always works.
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (_) { /* fall through to the legacy path */ }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch (_) {
    return false
  }
}
