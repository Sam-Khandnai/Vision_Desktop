import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowUp, Check, ChevronDown, ChevronRight, Copy, RotateCcw, Square, Wrench, X } from 'lucide-react'
import { ApiError, api, copyToClipboard, streamChatWithModel, streamRetry } from '../api'
import { useApp } from '../ctx'
import Mascot from './Mascot'
import Markdown from './Markdown'
import ModelPicker from './ModelPicker'
import { Spinner } from './ui'

const statusOf = (tool) => {
  if (tool.approval?.state === 'pending') return 'waiting'
  if (tool.ok === undefined || tool.ok === null) return tool.output === undefined ? 'running' : 'ok'
  if (tool.ok) return 'ok'
  return String(tool.output || '').startsWith('The user declined') ? 'declined' : 'failed'
}

function ToolCard({ tool, onAnswer }) {
  const { t } = useApp()
  const [open, setOpen] = useState(false)
  const status = statusOf(tool)
  const args = JSON.stringify(tool.args ?? {}, null, 2)
  return (
    <div className={`tool ${status}`}>
      <button className="tool-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Wrench size={14} />
        <span className="tool-name" dir="ltr">{tool.name}</span>
        <span className="tool-status">
          {status === 'running' && <><Spinner /> {t('toolRunning')}</>}
          {status === 'waiting' && t('toolWaiting')}
          {status === 'ok' && <><Check size={13} /> {t('toolDone')}</>}
          {status === 'failed' && <><AlertTriangle size={13} /> {t('toolFailed')}</>}
          {status === 'declined' && <><X size={13} /> {t('toolDeclined')}</>}
        </span>
      </button>

      {tool.approval?.state === 'pending' && (
        <div className="approval" role="alertdialog" aria-label={t('approvalTitle')}>
          <p className="approval-ask"><Mascot mood="curious" size={52} blink /> <span>{t('approvalAsk', { tool: tool.name, server: tool.approval.server })}</span></p>
          <pre dir="ltr">{args}</pre>
          <div className="row end">
            <button className="btn" onClick={() => onAnswer(tool, false)}>{t('deny')}</button>
            <button className="btn primary" onClick={() => onAnswer(tool, true)}>{t('allow')}</button>
          </div>
        </div>
      )}

      {open && (
        <div className="tool-body" dir="ltr">
          <div className="tool-label">{t('toolInput')}</div>
          <pre>{args}</pre>
          {tool.output !== undefined && (<><div className="tool-label">{t('toolOutput')}</div><pre>{tool.output}</pre></>)}
        </div>
      )}
    </div>
  )
}

function MessageActions({ text, canRetry, onCopy, onRetry }) {
  const { t } = useApp()
  const [done, setDone] = useState(false)
  const copy = async () => {
    await onCopy(text)
    setDone(true)
    setTimeout(() => setDone(false), 1500)
  }
  return (
    <div className="msg-actions">
      <button className="icon-btn small" onClick={copy} title={t('copy')} aria-label={t('copy')}>
        {done ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <button className="icon-btn small" onClick={onRetry} disabled={!canRetry} title={t('retry')} aria-label={t('retry')}>
        <RotateCcw size={14} />
      </button>
    </div>
  )
}

/* Minimal live status: shows what the assistant is doing while the answer is still empty. */
export function ActivityStrip({ toolName }) {
  const { t } = useApp()
  return (
    <div className="activity" role="status" aria-live="polite">
      <span className="activity-orb" aria-hidden="true"><i /><i /><i /></span>
      <span className="activity-label" dir="auto">
        {toolName ? t('callingTool', { name: toolName }) : t('thinking')}
      </span>
      <span className="activity-dots" aria-hidden="true"><b /><b /><b /></span>
    </div>
  )
}

function Message({ msg, onAnswer, streaming, canRetry, onCopy, onRetry }) {
  const actions = (msg.content || msg.error) && (
    <MessageActions text={msg.content || ''} canRetry={canRetry} onCopy={onCopy} onRetry={onRetry} />
  )
  if (msg.role === 'user') {
    return (
      <div className="msg user">
        <div className="bubble" dir="auto">{msg.content}</div>
        {actions}
      </div>
    )
  }
  const tools = msg.tools || []
  const waiting = tools.some((x) => x.approval?.state === 'pending')
  const running = tools.find((x) => statusOf(x) === 'running')
  // a tool that is still running is represented by the single activity line, not a card
  const settled = tools.filter((x) => statusOf(x) !== 'running')
  const busy = !msg.error && !waiting && (Boolean(running) || (streaming && !msg.content))
  const mood = msg.error ? 'sad' : waiting ? 'curious' : streaming ? (msg.content ? 'typing' : 'thinking') : 'normal'
  return (
    <div className="msg assistant">
      <div className="msg-avatar"><Mascot mood={mood} size={40} blink={!streaming} /></div>
      <div className="msg-body">
        {busy && <ActivityStrip toolName={running?.name} />}
        {msg.notice && <div className="notice-line">{msg.notice}</div>}
        {settled.map((tool) => <ToolCard key={tool.id} tool={tool} onAnswer={onAnswer} />)}
        {msg.content ? <div className="prose" dir="auto"><Markdown text={msg.content} /></div> : null}
        {msg.error && <div className="err-row"><AlertTriangle size={15} /> {msg.error}</div>}
        {msg.model_name && <div className="msg-model" dir="ltr" title={msg.model_name}>{msg.model_name}</div>}
        {actions}
      </div>
    </div>
  )
}

export default function Chat({ conversationId, providerReady, profile, providers, model, onModelChange, onCreated, onTouched, onOpenSettings }) {
  const { t, toast } = useApp()
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(false)
  const abortRef = useRef(null)
  const scroller = useRef(null)
  const stick = useRef(true)
  const skipLoad = useRef(null)
  const area = useRef(null)

  // load an existing conversation when selected (skip the one we are creating right now)
  useEffect(() => {
    if (!conversationId) { setMessages([]); return }
    if (skipLoad.current === conversationId) { skipLoad.current = null; return }
    let cancelled = false
    setLoading(true)
    api.get(`/api/conversations/${conversationId}`)
      .then((c) => {
        if (cancelled) return
        setMessages(c.messages)
        if (c.provider_id && c.model_name) onModelChange({ provider_id: c.provider_id, model_name: c.model_name }) // the chat remembers its model
      })
      .catch(() => toast(t('loadFailed'), 'error'))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [conversationId]) // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages])

  useLayoutEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 220) + 'px'
  }, [text])

  const onScroll = () => {
    const el = scroller.current
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const patchLast = useCallback((fn) => setMessages((m) => (m.length ? [...m.slice(0, -1), fn(m[m.length - 1])] : m)), [])
  const patchTool = (tools, id, fn) => tools.map((x) => (x.id === id ? fn(x) : x))

  const onEvent = useCallback((ev) => {
    if (ev.type === 'start') {
      patchLast((m) => ({ ...m, model_name: ev.model }))
      if (ev.user_message_id) {
        setMessages((m) => (m.length >= 2 ? [...m.slice(0, -2), { ...m[m.length - 2], id: ev.user_message_id }, m[m.length - 1]] : m))
      }
    }
    else if (ev.type === 'token') patchLast((m) => ({ ...m, content: (m.content || '') + ev.text }))
    else if (ev.type === 'tool_start') patchLast((m) => ({ ...m, tools: [...(m.tools || []), { id: ev.id, name: ev.name, args: ev.args }] }))
    else if (ev.type === 'tool_end') patchLast((m) => ({ ...m, tools: patchTool(m.tools || [], ev.id, (x) => ({ ...x, ok: ev.ok, output: ev.output, approval: x.approval ? { ...x.approval, state: x.approval.state === 'pending' ? 'allowed' : x.approval.state } : undefined })) }))
    else if (ev.type === 'approval_request') {
      patchLast((m) => {
        const tools = [...(m.tools || [])]
        for (let i = tools.length - 1; i >= 0; i--) {
          if (tools[i].name === ev.tool && tools[i].ok === undefined && !tools[i].approval) {
            tools[i] = { ...tools[i], approval: { id: ev.id, server: ev.server, state: 'pending' } }
            break
          }
        }
        return { ...m, tools }
      })
    } else if (ev.type === 'notice') patchLast((m) => ({ ...m, notice: ev.code === 'no_tools' ? t('noToolsNotice', { model: ev.model }) : '' }))
    else if (ev.type === 'error') patchLast((m) => ({ ...m, error: ev.code === 'local_unreachable' ? t('localUnreachable', { url: ev.url }) : ev.code === 'local_timeout' ? t('localTimeout') : ev.message }))
    else if (ev.type === 'done') {
      if (ev.message_id) patchLast((m) => ({ ...m, id: ev.message_id }))
      onTouched(ev.title)
    }
  }, [patchLast, onTouched, t])

  const answer = async (tool, approve) => {
    setMessages((ms) => ms.map((m) => ({ ...m, tools: (m.tools || []).map((x) => (x.id === tool.id ? { ...x, approval: { ...x.approval, state: approve ? 'allowed' : 'denied' } } : x)) })))
    try { await api.post(`/api/approvals/${tool.approval.id}`, { approve }) } catch (_) { toast(t('approvalFailed'), 'error') }
  }

  const copyText = async (content) => {
    if (await copyToClipboard(content)) toast(t('copied'))
    else toast(t('copyFailed'), 'error')
  }

  // Shared by "send" and "retry": replace the tail from `keep` on, then stream one turn.
  const runTurn = async (cid, keep, userText, call) => {
    stick.current = true
    setMessages((m) => [...m.slice(0, keep), { role: 'user', content: userText }, { role: 'assistant', content: '', tools: [] }])
    setStreaming(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await call(cid, ctrl.signal)
    } catch (e) {
      if (e.name === 'AbortError') { /* user pressed Stop */ }
      else if (e instanceof ApiError && e.message === 'no_provider') { patchLast((m) => ({ ...m, error: t('noProvider') })); onOpenSettings('provider') }
      else patchLast((m) => ({ ...m, error: e instanceof ApiError && e.status === 0 ? t('offline') : e.message }))
    } finally {
      setStreaming(false)
      abortRef.current = null
      onTouched()
    }
  }

  const send = async (override) => {
    const content = (override ?? text).trim()
    if (!content || streaming) return
    if (!providerReady) { onOpenSettings('provider'); return }
    setText('')
    let cid = conversationId
    try {
      if (!cid) {
        const c = await api.post('/api/conversations')
        cid = c.id
        skipLoad.current = cid
        onCreated(cid)
      }
    } catch (e) {
      toast(t('offline'), 'error'); setText(content); return
    }
    await runTurn(cid, messages.length, content, (id, signal) => streamChatWithModel(id, content, model, onEvent, signal))
  }

  const retry = async (index) => {
    if (streaming) return
    if (!providerReady) { onOpenSettings('provider'); return }
    if (!conversationId) return
    // for an assistant message, start again from the user message that produced it
    let start = index
    while (start > 0 && messages[start].role !== 'user') start--
    if (messages[start]?.role !== 'user') return
    const userText = messages[start].content
    const target = messages[start]
    if (!target.id) { toast(t('retryUnavailable'), 'error'); return }
    await runTurn(conversationId, start, userText, (id, signal) => streamRetry(id, target.id, onEvent, signal))
  }

  const stop = () => abortRef.current?.abort()

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() }
  }

  const empty = messages.length === 0 && !loading
  const name = profile.display_name

  return (
    <main className="chat">
      <div className="scroll" ref={scroller} onScroll={onScroll}>
        {empty ? (
          <div className="empty">
            <Mascot mood="happy" size={190} blink float />
            <h1 dir="auto">{name ? t('greetingNamed', { name }) : t('greeting')}</h1>
            <p className="muted">{t('emptyHint')}</p>
            <div className="chips">
              {['sugg1', 'sugg2', 'sugg3'].map((k) => (
                <button key={k} className="chip" onClick={() => { setText(t(k)); area.current?.focus() }}>{t(k)}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="thread">
            {messages.map((m, i) => (
              <Message
                key={m.id ?? `n${i}`} msg={m} onAnswer={answer} streaming={streaming && i === messages.length - 1}
                canRetry={!streaming && Boolean(m.id)} onCopy={copyText} onRetry={() => retry(i)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="composer-wrap">
        {!providerReady && (
          <button className="banner" onClick={() => onOpenSettings('provider')}>
            <AlertTriangle size={15} /> {t('noProviderBanner')}
          </button>
        )}
        <div className="composer">
          <div className="composer-model">
            <ModelPicker value={model} providers={providers} onChange={onModelChange} onManage={() => onOpenSettings('provider')} />
          </div>
          <textarea ref={area} dir="auto" rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} placeholder={t('composerPlaceholder')} aria-label={t('composerPlaceholder')} />
          {streaming ? (
            <button className="send stop" onClick={stop} aria-label={t('stop')} title={t('stop')}><Square size={15} fill="currentColor" /></button>
          ) : (
            <button className="send" onClick={() => send()} disabled={!text.trim()} aria-label={t('send')} title={t('send')}><ArrowUp size={18} /></button>
          )}
        </div>
        <p className="fineprint">{t('fineprint')}</p>
      </div>
    </main>
  )
}
