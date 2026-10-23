import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, initApi } from './api'
import { AppCtx } from './ctx'
import { initialLang, makeT } from './i18n'
import Catalog from './components/Catalog'
import Chat from './components/Chat'
import Mascot from './components/Mascot'
import UpdateBanner from './components/UpdateBanner'
import Settings from './components/Settings'
import Sidebar from './components/Sidebar'
import { Modal } from './components/ui'

export default function App() {
  const [lang, setLangState] = useState(initialLang)
  const t = useMemo(() => makeT(lang), [lang])
  const setLang = (l) => { localStorage.setItem('vision.lang', l); setLangState(l) }

  const [ready, setReady] = useState(false)
  const [fatal, setFatal] = useState(false)
  const [profile, setProfile] = useState({ display_name: '', about: '', instructions: '', memory_enabled: true })
  const [providers, setProviders] = useState([])
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [view, setView] = useState('chat')
  const [search, setSearch] = useState('')
  const [settings, setSettings] = useState(null) // null | tab name
  const [toastMsg, setToastMsg] = useState(null)
  const [confirmState, setConfirmState] = useState(null)
  const toastTimer = useRef(null)

  useEffect(() => { document.documentElement.lang = lang }, [lang])

  const toast = useCallback((text, kind = 'ok') => {
    setToastMsg({ text, kind })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToastMsg(null), kind === 'error' ? 6000 : 2500)
  }, [])

  const confirm = useCallback((text) => new Promise((resolve) => setConfirmState({ text, resolve })), [])

  const loadConversations = useCallback(async (q = search) => {
    try { setConversations(await api.get(`/api/conversations?q=${encodeURIComponent(q)}`)) } catch (_) {}
  }, [search])

  useEffect(() => {
    (async () => {
      try {
        await initApi()
        for (let i = 0; i < 40; i++) {
          try { await api.get('/api/system'); break } catch (e) { if (i === 39) throw e; await new Promise((r) => setTimeout(r, 250)) }
        }
        const [p, pr] = await Promise.all([api.get('/api/profile'), api.get('/api/providers')])
        setProfile(p); setProviders(pr)
        await loadConversations('')
        setReady(true)
        if (pr.length === 0) setSettings('provider') // first run: guide the user to connect a model
      } catch (_) { setFatal(true) }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ready) return
    const id = setTimeout(() => loadConversations(search), 200)
    return () => clearTimeout(id)
  }, [search, ready]) // eslint-disable-line react-hooks/exhaustive-deps

  // the model picker: the remembered choice, else the default provider's own model
  const [activeModel, setActiveModel] = useState(() => {
    try { return JSON.parse(localStorage.getItem('vision.model') || 'null') } catch (_) { return null }
  })
  const model = useMemo(() => {
    if (activeModel && providers.some((p) => p.id === activeModel.provider_id)) return activeModel
    const d = providers.find((p) => p.is_default) || providers[0]
    return d ? { provider_id: d.id, model_name: d.model_name } : null
  }, [activeModel, providers])
  const changeModel = (m) => { setActiveModel(m); localStorage.setItem('vision.model', JSON.stringify(m)) }
  const chosen = model && providers.find((p) => p.id === model.provider_id)
  const providerReady = !!(chosen && model.model_name && (chosen.local || chosen.has_key))

  const ctx = useMemo(() => ({ t, lang, setLang, toast, confirm }), [t, lang, toast, confirm])

  if (fatal) return <div className="splash"><Mascot mood="sad" size={140} /><p dir="auto">{t('engineDown')}</p></div>
  if (!ready) return <div className="splash"><Mascot mood="thinking" size={150} blink float /><div className="progress"><span /></div><p>{t('starting')}</p></div>

  const select = (id) => { setActiveId(id); setView('chat') }
  const rename = async (id, title) => { await api.patch(`/api/conversations/${id}`, { title }); loadConversations() }
  const remove = async (id) => {
    if (!(await confirm(t('deleteChatConfirm')))) return
    await api.del(`/api/conversations/${id}`)
    if (id === activeId) setActiveId(null)
    loadConversations()
  }

  return (
    <AppCtx.Provider value={ctx}>
      <div className="app">
        <Sidebar
          conversations={conversations} activeId={activeId} view={view} search={search} setSearch={setSearch}
          onSelect={select} onNew={() => { setActiveId(null); setView('chat') }} onRename={rename} onDelete={remove}
          onCatalog={() => setView('catalog')} onSettings={(tab) => setSettings(typeof tab === 'string' ? tab : 'account')} profile={profile}
          lang={lang} onToggleLang={() => setLang(lang === 'fa' ? 'en' : 'fa')}
        />
        {view === 'catalog' ? (
          <Catalog onBack={() => setView('chat')} />
        ) : (
          <Chat
            conversationId={activeId} providerReady={providerReady} profile={profile}
            providers={providers} model={model} onModelChange={changeModel}
            onCreated={(id) => setActiveId(id)} onTouched={() => loadConversations()}
            onOpenSettings={(tab) => setSettings(tab || 'account')}
          />
        )}
      </div>

      {settings && (
        <Settings
          key={settings} initialTab={settings} onClose={() => setSettings(null)}
          onProfileChanged={setProfile} onProvidersChanged={setProviders}
          onOpenCatalog={() => setView('catalog')}
        />
      )}

      <UpdateBanner />

      {confirmState && (
        <Modal title={t('confirmTitle')} onClose={() => { confirmState.resolve(false); setConfirmState(null) }}
          footer={<>
            <button className="btn" onClick={() => { confirmState.resolve(false); setConfirmState(null) }}>{t('cancel')}</button>
            <button className="btn primary" autoFocus onClick={() => { confirmState.resolve(true); setConfirmState(null) }}>{t('confirm')}</button>
          </>}>
          <p dir="auto">{confirmState.text}</p>
        </Modal>
      )}

      {toastMsg && <div className={`toast ${toastMsg.kind}`} role="status" dir="auto"><Mascot mood={toastMsg.kind === 'error' ? 'sad' : 'happy'} size={38} /><span>{toastMsg.text}</span></div>}
    </AppCtx.Provider>
  )
}
