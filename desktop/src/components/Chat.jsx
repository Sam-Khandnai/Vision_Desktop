import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowUp, Check, ChevronDown, ChevronRight, ShieldQuestion, Square, Wrench, X } from 'lucide-react'
import { ApiError, api, streamChat } from '../api'
import { useApp } from '../ctx'
import Mascot from './Mascot'
import Markdown from './Markdown'
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

function Message({ msg, onAnswer, streaming }) {
  if (msg.role === 'user') {
    return <div className="msg user"><div className="bubble" dir="auto">{msg.content}</div></div>
  }
  const tools = msg.tools || []
  const waiting = tools.some((x) => x.approval?.state === 'pending')
  const mood = msg.error ? 'sad' : waiting ? 'curious' : streaming ? (msg.content ? 'typing' : 'thinking') : 'normal'
  return (
    <div className="msg assistant">
      <div className="msg-avatar"><Mascot mood={mood} size={40} blink={!streaming} /></div>
      <div className="msg-body">
        {tools.map((tool) => <ToolCard key={tool.id} tool={tool} onAnswer={onAnswer} />)}
        {msg.content ? <div className="prose" dir="auto"><Markdown text={msg.content} /></div> : null}
        {msg.error && <div className="err-row"><AlertTriangle size={15} /> {msg.error}</div>}
      </div>
    </div>
  )
}

export default function Chat({ conversationId, providerReady, profile, onCreated, onTouched, onOpenSettings }) {
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
      .then((c) => { if (!cancelled) setMessages(c.messages) })
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
    if (ev.type === 'token') patchLast((m) => ({ ...m, content: (m.content || '') + ev.text }))
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
    } else if (ev.type === 'error') patchLast((m) => ({ ...m, error: ev.message }))
    else if (ev.type === 'done') onTouched(ev.title)
  }, [patchLast, onTouched])

  const answer = async (tool, approve) => {
    setMessages((ms) => ms.map((m) => ({ ...m, tools: (m.tools || []).map((x) => (x.id === tool.id ? { ...x, approval: { ...x.approval, state: approve ? 'allowed' : 'denied' } } : x)) })))
    try { await api.post(`/api/approvals/${tool.approval.id}`, { approve }) } catch (_) { toast(t('approvalFailed'), 'error') }
  }

  const send = async (override) => {
    const content = (override ?? text).trim()
    if (!content || streaming) return
    if (!providerReady) { onOpenSettings('provider'); return }
    setText('')
    stick.current = true
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
    setMessages((m) => [...m, { role: 'user', content }, { role: 'assistant', content: '', tools: [] }])
    setStreaming(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await streamChat(cid, content, onEvent, ctrl.signal)
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
              <Message key={m.id ?? `n${i}`} msg={m} onAnswer={answer} streaming={streaming && i === messages.length - 1} />
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
