import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Check, ExternalLink, Search, TriangleAlert } from 'lucide-react'
import { api, openExternal } from '../api'
import { useApp } from '../ctx'
import { loc } from '../i18n'
import { Field, Modal, PathInput, Spinner } from './ui'
import Mascot from './Mascot'

function InstallModal({ entry, runtimes, onClose, onInstalled }) {
  const { t, toast, lang } = useApp()
  const [values, setValues] = useState(() => Object.fromEntries(entry.inputs.map((i) => [i.key, i.default || ''])))
  const [approval, setApproval] = useState('smart')
  const [busy, setBusy] = useState(false)
  const missing = entry.requires && !runtimes[entry.requires]

  const install = async () => {
    setBusy(true)
    try {
      await api.post(`/api/catalog/${entry.id}/install`, { values, approval })
      toast(t('added')); onInstalled()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <Modal title={t('addServerTitle', { name: entry.name })} onClose={onClose} footer={
      <>
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn primary" onClick={install} disabled={busy}>{busy ? <Spinner /> : t('addServer')}</button>
      </>
    }>
      <p dir="auto">{loc(entry.description, lang)}</p>
      {entry.note && <div className="notice"><TriangleAlert size={16} /> {loc(entry.note, lang)}</div>}
      {missing && <div className="notice"><TriangleAlert size={16} /> {entry.requires === 'node' ? t('noNode') : t('noUv')}</div>}
      {entry.risk === 'high' && <div className="notice danger"><TriangleAlert size={16} /> {t('riskHighWarn')}</div>}
      {entry.inputs.map((inp) => (
        <Field key={inp.key} label={loc(inp.label, lang) + (inp.required === false ? ` (${t('optional')})` : '')} help={inp.help ? loc(inp.help, lang) : undefined}>
          {inp.type === 'path' ? (
            <PathInput kind={inp.key.includes('file') ? 'file' : 'folder'} value={values[inp.key]} onChange={(v) => setValues({ ...values, [inp.key]: v })} />
          ) : (
            <input dir="ltr" type={inp.type === 'secret' ? 'password' : 'text'} autoComplete="off" value={values[inp.key]} onChange={(e) => setValues({ ...values, [inp.key]: e.target.value })} spellCheck={false} />
          )}
        </Field>
      ))}
      {entry.inputs.length === 0 && <p className="muted">{t('noSetupNeeded')}</p>}
      <Field label={t('approvalMode')} help={t('approvalHelp')}>
        <select value={approval} onChange={(e) => setApproval(e.target.value)}>
          <option value="smart">{t('approval_smart')}</option><option value="always">{t('approval_always')}</option><option value="never">{t('approval_never')}</option>
        </select>
      </Field>
      <button className="link" onClick={() => openExternal(entry.docs)}><ExternalLink size={13} /> {t('docs')}</button>
    </Modal>
  )
}

export default function Catalog({ onBack }) {
  const { t, toast, lang } = useApp()
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('all')
  const [picked, setPicked] = useState(null)

  const load = () => api.get('/api/catalog').then(setData).catch(() => toast(t('offline'), 'error'))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const shown = useMemo(() => {
    if (!data) return []
    const needle = q.trim().toLowerCase()
    return data.servers.filter((s) => (cat === 'all' || s.category === cat) && (!needle || (s.name + s.id + s.description.fa + s.description.en).toLowerCase().includes(needle)))
  }, [data, q, cat])

  if (!data) return <main className="page"><div className="center pad"><Spinner /></div></main>

  return (
    <main className="page">
      <div className="page-inner">
        <header className="page-head">
          <button className="icon-btn" onClick={onBack} aria-label={t('back')}><ArrowLeft size={18} /></button>
          <div>
            <h1>{t('catalogTitle')}</h1>
            <p className="muted">{t('catalogSubtitle', { n: data.servers.length })}</p>
          </div>
        </header>

        <div className="search wide"><Search size={15} /><input dir="auto" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('catalogSearch')} /></div>
        <div className="chips left">
          <button className={`chip${cat === 'all' ? ' on' : ''}`} onClick={() => setCat('all')}>{t('all')}</button>
          {Object.entries(data.categories).map(([k, label]) => (
            <button key={k} className={`chip${cat === k ? ' on' : ''}`} onClick={() => setCat(k)}>{loc(label, lang)}</button>
          ))}
        </div>

        {shown.length === 0 && <div className="empty-note"><Mascot mood="surprised" size={110} blink /><p>{t('noResults')}</p></div>}
        <div className="grid">
          {shown.map((s) => (
            <article key={s.id} className="mcp-card">
              <div className="row between">
                <h3 dir="ltr">{s.name}</h3>
                <span className={`badge risk-${s.risk}`}>{t('risk_' + s.risk)}</span>
              </div>
              <p dir="auto">{loc(s.description, lang)}</p>
              <div className="meta">
                <span>{loc(data.categories[s.category], lang)}</span>
                <span>{s.transport === 'stdio' ? t('local') : t('remote')}</span>
                {s.requires && <span className={data.runtimes[s.requires] ? '' : 'missing'}>{s.requires === 'node' ? 'Node.js' : 'uv'}</span>}
              </div>
              <div className="row between">
                <button className="link" onClick={() => openExternal(s.docs)}><ExternalLink size={13} /> {t('docs')}</button>
                {s.installed ? <span className="badge accent"><Check size={12} /> {t('installed')}</span> : <button className="btn primary small" onClick={() => setPicked(s)}>{t('add')}</button>}
              </div>
            </article>
          ))}
        </div>
      </div>
      {picked && <InstallModal entry={picked} runtimes={data.runtimes} onClose={() => setPicked(null)} onInstalled={() => { setPicked(null); load() }} />}
    </main>
  )
}
