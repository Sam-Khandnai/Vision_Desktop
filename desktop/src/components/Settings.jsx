import { useCallback, useEffect, useState } from 'react'
import { Check, ChevronDown, ChevronRight, LayoutGrid, Plug, RefreshCw, Trash2, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../ctx'
import { Field, Modal, PathInput, Spinner, Toggle } from './ui'
import Mascot, { MascotIcon } from './Mascot'

const TABS = ['account', 'provider', 'mcp']
const TAB_ICON = { account: 'account', provider: 'model', mcp: 'mcp' }

export default function Settings({ initialTab = 'account', onClose, onProfileChanged, onProvidersChanged, onOpenCatalog }) {
  const { t } = useApp()
  const [tab, setTab] = useState(initialTab)
  return (
    <Modal title={t('settings')} onClose={onClose} wide>
      <div className="tabs" role="tablist">
        {TABS.map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? ' active' : ''}`} onClick={() => setTab(k)}>
            <MascotIcon name={TAB_ICON[k]} size={20} />{t('tab_' + k)}
          </button>
        ))}
      </div>
      {tab === 'account' && <AccountTab onProfileChanged={onProfileChanged} />}
      {tab === 'provider' && <ProviderTab onProvidersChanged={onProvidersChanged} />}
      {tab === 'mcp' && <McpTab onOpenCatalog={() => { onClose(); onOpenCatalog() }} />}
    </Modal>
  )
}

/* ---------------------------------------------------------------- account */
function AccountTab({ onProfileChanged }) {
  const { t, toast, confirm, lang, setLang } = useApp()
  const [p, setP] = useState(null)
  const [memories, setMemories] = useState([])
  const [newFact, setNewFact] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setP(await api.get('/api/profile'))
    setMemories(await api.get('/api/memories'))
  }, [])
  useEffect(() => { load().catch(() => toast(t('offline'), 'error')) }, [load]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!p) return <div className="center pad"><Spinner /></div>

  const save = async () => {
    setSaving(true)
    try {
      const saved = await api.put('/api/profile', { display_name: p.display_name, about: p.about, instructions: p.instructions })
      setP(saved); onProfileChanged(saved); toast(t('saved'))
    } catch (e) { toast(e.message, 'error') } finally { setSaving(false) }
  }
  const toggleMemory = async (v) => {
    const saved = await api.put('/api/settings', { memory_enabled: v })
    setP(saved); onProfileChanged(saved)
  }
  const addFact = async () => {
    if (newFact.trim().length < 2) return
    await api.post('/api/memories', { text: newFact.trim() })
    setNewFact(''); setMemories(await api.get('/api/memories'))
  }
  const delFact = async (id) => { await api.del(`/api/memories/${id}`); setMemories((m) => m.filter((x) => x.id !== id)) }
  const clearAll = async () => {
    if (!(await confirm(t('clearMemoriesConfirm')))) return
    await api.del('/api/memories'); setMemories([])
  }

  return (
    <div className="tab-body">
      <section>
        <h3>{t('aboutYou')}</h3>
        <p className="muted">{t('aboutYouHint')}</p>
        <Field label={t('displayName')}>
          <input dir="auto" value={p.display_name} maxLength={80} onChange={(e) => setP({ ...p, display_name: e.target.value })} placeholder={t('displayNamePh')} />
        </Field>
        <Field label={t('aboutMe')}>
          <textarea dir="auto" rows={4} value={p.about} maxLength={2000} onChange={(e) => setP({ ...p, about: e.target.value })} placeholder={t('aboutMePh')} />
        </Field>
        <Field label={t('customInstructions')} help={t('customInstructionsHelp')}>
          <textarea dir="auto" rows={3} value={p.instructions} maxLength={2000} onChange={(e) => setP({ ...p, instructions: e.target.value })} placeholder={t('customInstructionsPh')} />
        </Field>
        <div className="row end"><button className="btn primary" onClick={save} disabled={saving}>{saving ? <Spinner /> : t('save')}</button></div>
      </section>

      <section>
        <div className="row between">
          <div>
            <h3 className="row gap"><MascotIcon name="memory" size={22} /> {t('memoryTitle')}</h3>
            <p className="muted">{t('memoryHint')}</p>
          </div>
          <Toggle checked={p.memory_enabled} onChange={toggleMemory} label={t('memoryTitle')} />
        </div>
        <div className="row gap">
          <input dir="auto" className="grow" value={newFact} onChange={(e) => setNewFact(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addFact()} placeholder={t('addMemoryPh')} />
          <button className="btn" onClick={addFact}>{t('add')}</button>
        </div>
        {memories.length === 0 ? <p className="muted pad">{t('noMemories')}</p> : (
          <ul className="mem-list">
            {memories.map((m) => (
              <li key={m.id}>
                <span dir="auto">{m.text}</span>
                <button className="icon-btn small" aria-label={t('delete')} onClick={() => delFact(m.id)}><Trash2 size={14} /></button>
              </li>
            ))}
          </ul>
        )}
        {memories.length > 0 && <div className="row end"><button className="btn danger-text" onClick={clearAll}>{t('clearMemories')}</button></div>}
      </section>

      <section>
        <h3>{t('language')}</h3>
        <div className="row gap">
          {[['fa', 'فارسی'], ['en', 'English']].map(([k, label]) => (
            <button key={k} className={`btn${lang === k ? ' primary' : ''}`} onClick={() => setLang(k)}>{label}</button>
          ))}
        </div>
      </section>
    </div>
  )
}

/* --------------------------------------------------------------- provider */
const LOCAL_PRESETS = [
  ['Ollama', 'http://localhost:11434/v1'],
  ['LM Studio', 'http://localhost:1234/v1'],
  ['llama.cpp', 'http://localhost:8080/v1'],
  ['vLLM', 'http://localhost:8000/v1'],
  ['Jan', 'http://localhost:1337/v1'],
]
const CLOUD_PRESETS = [
  ['OpenAI', 'https://api.openai.com/v1'],
  ['OpenRouter', 'https://openrouter.ai/api/v1'],
  ['Groq', 'https://api.groq.com/openai/v1'],
  ['DeepSeek', 'https://api.deepseek.com/v1'],
  ['Together', 'https://api.together.xyz/v1'],
]
const BLANK = { id: null, name: '', base_url: '', api_key: '', model_name: '', has_key: false, local: false, context_tokens: '' }

function ProviderTab({ onProvidersChanged }) {
  const { t, toast, confirm } = useApp()
  const [list, setList] = useState(null)
  const [form, setForm] = useState(null)
  const [models, setModels] = useState([])
  const [found, setFound] = useState(null) // result of "detect local servers": null = not searched yet
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    const l = await api.get('/api/providers')
    setList(l); onProvidersChanged(l)
  }, [onProvidersChanged])
  useEffect(() => { load().catch(() => toast(t('offline'), 'error')) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (!list) return <div className="center pad"><Spinner /></div>

  const body = () => ({ base_url: form.base_url, api_key: form.api_key, provider_id: form.id, local: form.local })
  const fetchModels = async () => {
    setBusy('models')
    try { setModels((await api.post('/api/providers/models', body())).models); } catch (e) { toast(t('modelsFailed') + ' ' + e.message, 'error') } finally { setBusy('') }
  }
  const detect = async () => {
    setBusy('detect')
    try { setFound((await api.get('/api/providers/detect-local')).servers) } catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }
  const pickFound = (s) => {
    setForm({ ...form, local: true, name: form.name || s.name, base_url: s.base_url, model_name: form.model_name || s.models[0] || '' })
    setModels(s.models)
  }
  const testConn = async () => {
    setBusy('test')
    try { await api.post('/api/providers/test', { ...body(), model_name: form.model_name }); toast(t('testOk')) } catch (e) { toast(t('testFailed') + ' ' + e.message, 'error') } finally { setBusy('') }
  }
  const save = async () => {
    setBusy('save')
    try {
      const payload = { name: form.name, base_url: form.base_url, model_name: form.model_name, api_key: form.api_key,
        local: form.local, context_tokens: Number(form.context_tokens) || 0 }
      if (form.id) await api.put(`/api/providers/${form.id}`, payload)
      else await api.post('/api/providers', payload)
      setForm(null); setModels([]); setFound(null); await load(); toast(t('saved'))
    } catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }
  const remove = async (p) => {
    if (!(await confirm(t('deleteProviderConfirm', { name: p.name })))) return
    await api.del(`/api/providers/${p.id}`); load()
  }

  if (form) {
    return (
      <div className="tab-body">
        <h3>{form.id ? t('editProvider') : t('addProvider')}</h3>
        {!form.id && (
          <>
            <div className="preset-group">
              <span className="muted small">{t('presetsLocal')}</span>
              <div className="chips left">
                {LOCAL_PRESETS.map(([n, u]) => <button key={n} className="chip" onClick={() => setForm({ ...form, local: true, base_url: u, name: form.name || n })}>{n}</button>)}
              </div>
              <div className="row gap wrap">
                <button className="btn" onClick={detect} disabled={busy === 'detect'}>{busy === 'detect' ? <Spinner /> : null} {t('detectLocal')}</button>
                {found && found.length === 0 && <span className="muted small">{t('detectNone')}</span>}
              </div>
              {found && found.length > 0 && (
                <div className="chips left">
                  {found.map((s) => <button key={s.base_url} className="chip on" onClick={() => pickFound(s)}>{s.name}{' · '}{t('detectFound', { n: s.models.length })}</button>)}
                </div>
              )}
            </div>
            <div className="preset-group">
              <span className="muted small">{t('presetsCloud')}</span>
              <div className="chips left">
                {CLOUD_PRESETS.map(([n, u]) => <button key={n} className="chip" onClick={() => setForm({ ...form, local: false, base_url: u, name: form.name || n })}>{n}</button>)}
              </div>
            </div>
          </>
        )}
        <Field label={t('providerName')}><input dir="auto" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="OpenRouter" /></Field>
        <Field label="Base URL" help={form.local ? t('localModelHelp') : t('baseUrlHelp')}><input dir="ltr" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.example.com/v1" spellCheck={false} /></Field>
        <div className="row between local-row">
          <div><span className="strong">{t('localModel')}</span><p className="muted small">{t('localModelHint')}</p></div>
          <Toggle checked={form.local} label={t('localModel')} onChange={(v) => setForm({ ...form, local: v })} />
        </div>
        {!form.local && (
        <Field label={t('apiKey')} help={form.has_key ? t('apiKeyStored') : t('apiKeyHelp')}>
          <input dir="ltr" type="password" autoComplete="off" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder={form.has_key ? '••••••••••••' : 'sk-…'} />
        </Field>
        )}
        {form.local && (
          <Field label={t('contextTokens')} help={t('contextHelp')}>
            <input dir="ltr" type="number" min="512" step="512" value={form.context_tokens ?? ''} onChange={(e) => setForm({ ...form, context_tokens: e.target.value })} placeholder="4096" />
          </Field>
        )}
        <Field label={t('modelId')}>
          <div className="row gap">
            <input dir="ltr" className="grow" list="model-options" value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} placeholder="provider-model-id" spellCheck={false} />
            <button className="btn" onClick={fetchModels} disabled={busy === 'models' || !form.base_url}>{busy === 'models' ? <Spinner /> : t('listModels')}</button>
          </div>
          <datalist id="model-options">{models.map((m) => <option key={m} value={m} />)}</datalist>
        </Field>
        {models.length > 0 && <p className="muted">{t('modelsFound', { n: models.length })}</p>}
        <div className="row between">
          <button className="btn" onClick={testConn} disabled={busy === 'test' || !form.base_url || !form.model_name}>{busy === 'test' ? <Spinner /> : t('testConnection')}</button>
          <div className="row gap">
            <button className="btn" onClick={() => { setForm(null); setModels([]); setFound(null) }}>{t('cancel')}</button>
            <button className="btn primary" onClick={save} disabled={busy === 'save' || !form.base_url}>{busy === 'save' ? <Spinner /> : t('save')}</button>
          </div>
        </div>
        <p className="muted">{form.local ? t('localNote') : t('keychainNote')}</p>
      </div>
    )
  }

  return (
    <div className="tab-body">
      <div className="row between">
        <div><h3>{t('providers')}</h3><p className="muted">{t('providersHint')}</p></div>
        <button className="btn primary" onClick={() => setForm({ ...BLANK })}>{t('addProvider')}</button>
      </div>
      {list.length === 0 ? <p className="muted pad">{t('noProviders')}</p> : (
        <ul className="cards">
          {list.map((p) => (
            <li key={p.id} className="card-row">
              <div className="grow">
                <div className="strong" dir="auto">{p.name} {p.local && <span className="badge">{t('localBadge')}</span>} {p.is_default && <span className="badge accent">{t('active')}</span>} {!p.ready && <span className="badge risk-medium">{t('notReady')}</span>}</div>
                <div className="muted small" dir="ltr">{p.model_name || '—'} · {p.base_url}</div>
              </div>
              {!p.is_default && <button className="btn" onClick={async () => { await api.post(`/api/providers/${p.id}/default`); load() }}>{t('makeActive')}</button>}
              <button className="btn" onClick={() => setForm({ ...p, api_key: '', context_tokens: p.context_tokens || '' })}>{t('edit')}</button>
              <button className="icon-btn" aria-label={t('delete')} onClick={() => remove(p)}><Trash2 size={16} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------- mcp */
const parseLines = (text, sep) => {
  const out = {}
  text.split('\n').map((l) => l.trim()).filter(Boolean).forEach((l) => {
    const i = l.indexOf(sep)
    if (i > 0) out[l.slice(0, i).trim()] = l.slice(i + 1).trim()
  })
  return out
}
const DOT = { connected: 'ok', connecting: 'wait', idle: 'wait', error: 'bad', disabled: 'off' }
const MOOD_OF = { connected: 'normal', connecting: 'thinking', idle: 'thinking', error: 'sad', disabled: 'sleepy' }
const BADGE_OF = { connected: 'online', error: 'error', disabled: 'disabled' }

function McpTab({ onOpenCatalog }) {
  const { t, toast, confirm } = useApp()
  const [servers, setServers] = useState(null)
  const [sys, setSys] = useState(null)
  const [open, setOpen] = useState({})
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ name: '', transport: 'stdio', command: '', args: '', env: '', url: '', headers: '', approval: 'smart' })

  const load = useCallback(async () => setServers(await api.get('/api/mcp/servers')), [])
  useEffect(() => {
    load().catch(() => toast(t('offline'), 'error'))
    api.get('/api/system').then(setSys).catch(() => {})
    const id = setInterval(() => load().catch(() => {}), 2000)
    return () => clearInterval(id)
  }, [load]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!servers) return <div className="center pad"><Spinner /></div>

  const add = async () => {
    try {
      const body = f.transport === 'stdio'
        ? { name: f.name, transport: 'stdio', command: f.command, args: f.args.split('\n').map((x) => x.trim()).filter(Boolean), env: parseLines(f.env, '='), approval: f.approval }
        : { name: f.name, transport: f.transport, url: f.url, headers: parseLines(f.headers, ':'), approval: f.approval }
      await api.post('/api/mcp/servers', body)
      setAdding(false); setF({ ...f, name: '', command: '', args: '', env: '', url: '', headers: '' }); load(); toast(t('added'))
    } catch (e) { toast(e.message, 'error') }
  }
  const remove = async (s) => { if (await confirm(t('deleteServerConfirm', { name: s.name }))) { await api.del(`/api/mcp/servers/${s.id}`); load() } }

  return (
    <div className="tab-body">
      <button className="catalog-cta" onClick={onOpenCatalog}>
        <MascotIcon name="catalog" size={30} />
        <span><strong>{t('browseCatalog')}</strong><small>{t('browseCatalogHint')}</small></span>
      </button>

      {sys && (!sys.runtimes.node || !sys.runtimes.uv) && (
        <div className="notice"><TriangleAlert size={16} /> {!sys.runtimes.node && t('noNode')} {!sys.runtimes.uv && t('noUv')}</div>
      )}

      <div className="row between">
        <h3>{t('connectedServers')}</h3>
        <button className="btn" onClick={() => setAdding(!adding)}>{adding ? t('cancel') : t('addManually')}</button>
      </div>

      {adding && (
        <div className="subform">
          <Field label={t('serverName')}><input dir="auto" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="filesystem" /></Field>
          <Field label={t('transport')}>
            <select value={f.transport} onChange={(e) => setF({ ...f, transport: e.target.value })}>
              <option value="stdio">stdio ({t('local')})</option><option value="streamable_http">streamable_http ({t('remote')})</option><option value="sse">sse ({t('remote')})</option>
            </select>
          </Field>
          {f.transport === 'stdio' ? (<>
            <Field label={t('command')}><input dir="ltr" value={f.command} onChange={(e) => setF({ ...f, command: e.target.value })} placeholder="npx" /></Field>
            <Field label={t('argsLines')}><textarea dir="ltr" rows={3} value={f.args} onChange={(e) => setF({ ...f, args: e.target.value })} placeholder={'-y\n@modelcontextprotocol/server-filesystem\nC:\\my_project'} /></Field>
            <Field label={t('envLines')}><textarea dir="ltr" rows={2} value={f.env} onChange={(e) => setF({ ...f, env: e.target.value })} placeholder="API_KEY=…" /></Field>
          </>) : (<>
            <Field label="URL"><input dir="ltr" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://server.example.com/mcp" /></Field>
            <Field label={t('headersLines')}><textarea dir="ltr" rows={2} value={f.headers} onChange={(e) => setF({ ...f, headers: e.target.value })} placeholder="Authorization: Bearer …" /></Field>
          </>)}
          <div className="row end"><button className="btn primary" onClick={add}>{t('add')}</button></div>
        </div>
      )}

      {servers.length === 0 ? <p className="muted pad">{t('noServers')}</p> : (
        <ul className="cards">
          {servers.map((s) => (
            <li key={s.id} className="card-col">
              <div className="card-row">
                <span className="server-face" title={s.status.state}><Mascot size={44} mood={MOOD_OF[s.status.state] || 'normal'} status={BADGE_OF[s.status.state]} /></span>
                <div className="grow">
                  <div className="strong" dir="auto">{s.name}</div>
                  <div className="muted small">{t('state_' + s.status.state)}{s.status.state === 'connected' ? ` · ${s.status.tool_count} ${t('tools')}` : ''}</div>
                </div>
                <button className="icon-btn" onClick={() => setOpen({ ...open, [s.id]: !open[s.id] })} aria-label={t('details')}>{open[s.id] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>
                <Toggle checked={s.enabled} label={s.name} onChange={async (v) => { await api.post(`/api/mcp/servers/${s.id}/enabled`, { enabled: v }); load() }} />
              </div>
              {s.status.state === 'error' && <div className="inline-error" dir="ltr"><TriangleAlert size={14} /> {s.status.message}</div>}
              {open[s.id] && (
                <div className="details">
                  <label className="row gap small">
                    <span className="muted">{t('approvalMode')}</span>
                    <select value={s.approval} onChange={async (e) => { await api.post(`/api/mcp/servers/${s.id}/approval`, { approval: e.target.value }); load() }}>
                      <option value="smart">{t('approval_smart')}</option><option value="always">{t('approval_always')}</option><option value="never">{t('approval_never')}</option>
                    </select>
                  </label>
                  <p className="muted small" dir="ltr">{s.transport === 'stdio' ? `${s.command} ${s.args.join(' ')}` : s.url}</p>
                  {s.status.tools.length > 0 && <p className="tool-list" dir="ltr">{s.status.tools.join(' · ')}</p>}
                  <div className="row end gap">
                    <button className="btn" onClick={async () => { await api.post(`/api/mcp/servers/${s.id}/connect`); load() }}><RefreshCw size={14} /> {t('reconnect')}</button>
                    <button className="btn danger-text" onClick={() => remove(s)}><Trash2 size={14} /> {t('delete')}</button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small"><Plug size={13} /> {t('mcpSecurity')}</p>
    </div>
  )
}
