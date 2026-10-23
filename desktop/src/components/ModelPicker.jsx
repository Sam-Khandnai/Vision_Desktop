import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronUp, Cpu, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../ctx'
import { Spinner } from './ui'

const MAX_SHOWN = 120

function detailText(d) {
  if (!d) return ''
  const parts = [d.params, d.quant]
  if (d.size) parts.push(`${(d.size / 1e9).toFixed(1)} GB`)
  return parts.filter(Boolean).join(' \u00b7 ')
}

// Shows the model that answers the next message, and lets you switch to any model of any provider.
export default function ModelPicker({ value, providers, onChange, onManage }) {
  const { t } = useApp()
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const box = useRef(null)

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    try { setData((await api.get(`/api/models${refresh ? '?refresh=true' : ''}`)).providers) } catch (_) { setData([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => { if (open) { setQuery(''); load(false) } }, [open, load])
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const current = providers.find((p) => p.id === value?.provider_id)
  const needle = query.trim().toLowerCase()
  const groups = (data || [])
    .map((g) => ({ ...g, shown: g.models.filter((m) => !needle || m.id.toLowerCase().includes(needle) || g.name.toLowerCase().includes(needle)) }))
    .filter((g) => g.shown.length || (!needle && g.error))

  return (
    <div className="model-picker" ref={box}>
      <button className="model-btn" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}
        title={value ? `${current ? current.name + ' \u00b7 ' : ''}${value.model_name}` : t('modelChoose')}>
        <Cpu size={14} />
        <span className="model-name" dir="ltr">{value?.model_name || t('modelChoose')}</span>
        {current && <span className="model-provider" dir="auto">{current.name}</span>}
        {current && current.local && <span className="badge">{t('localBadge')}</span>}
        <ChevronUp size={14} className={open ? '' : 'flip'} />
      </button>

      {open && (
        <div className="model-pop">
          <div className="model-pop-head">
            <input autoFocus dir="auto" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('modelSearch')} />
            <button className="icon-btn" onClick={() => load(true)} aria-label={t('modelsRefresh')} title={t('modelsRefresh')}>
              <RefreshCw size={15} className={loading ? 'spin' : ''} />
            </button>
          </div>
          <div className="model-list" role="listbox" aria-label={t('modelChoose')}>
            {data === null && <div className="center pad"><Spinner /></div>}
            {data && data.length === 0 && <p className="muted pad">{t('modelNoneYet')}</p>}
            {groups.map((g) => (
              <div key={g.provider_id} className="model-group">
                <div className="model-group-title">
                  <span dir="auto">{g.name}</span>
                  {g.kind === 'local' && <span className="badge">{t('localBadge')}</span>}
                  <span className="muted small">{g.models.length}</span>
                </div>
                {g.error && <div className="model-error" dir="auto">{t('modelsUnreachable', { name: g.name })}</div>}
                {g.shown.slice(0, MAX_SHOWN).map((m) => {
                  const active = value?.provider_id === g.provider_id && value?.model_name === m.id
                  return (
                    <button key={m.id} role="option" aria-selected={active} className={`model-item${active ? ' on' : ''}`}
                      onClick={() => { onChange({ provider_id: g.provider_id, model_name: m.id }); setOpen(false) }}>
                      <span className="model-id" dir="ltr">{m.id}</span>
                      <span className="model-meta" dir="ltr">{detailText(m.details)}</span>
                      {active && <Check size={14} />}
                    </button>
                  )
                })}
                {g.shown.length > MAX_SHOWN && <div className="muted small pad">{t('modelsMore', { n: g.shown.length - MAX_SHOWN })}</div>}
              </div>
            ))}
            {data && data.length > 0 && groups.length === 0 && <p className="muted pad">{t('modelsNoMatch')}</p>}
          </div>
          <button className="model-manage" onClick={() => { setOpen(false); onManage() }}>{t('modelsManage')}</button>
        </div>
      )}
    </div>
  )
}
