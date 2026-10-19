import { useMemo, useState } from 'react'
import { Languages, LayoutGrid, Pencil, Plus, Search, Settings, Trash2 } from 'lucide-react'
import { useApp } from '../ctx'
import Mascot, { MascotIcon } from './Mascot'

function groupOf(ts) {
  const day = 86400000
  const startToday = new Date().setHours(0, 0, 0, 0)
  const t = ts * 1000
  if (t >= startToday) return 'today'
  if (t >= startToday - day) return 'yesterday'
  if (t >= startToday - 7 * day) return 'week'
  return 'older'
}

export default function Sidebar({ conversations, activeId, view, search, setSearch, onSelect, onNew, onRename, onDelete, onCatalog, onSettings, profile, lang, onToggleLang }) {
  const { t } = useApp()
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')

  const groups = useMemo(() => {
    const out = { today: [], yesterday: [], week: [], older: [] }
    conversations.forEach((c) => out[groupOf(c.updated_at)].push(c))
    return out
  }, [conversations])

  const name = profile.display_name || t('guest')
  const initial = Array.from(name)[0]?.toUpperCase() || '?'

  const commit = (id) => {
    const title = draft.trim()
    setEditing(null)
    if (title) onRename(id, title)
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <Mascot mood="normal" size={46} blink />
        <span>Vision</span>
      </div>

      <button className="new-chat" onClick={onNew}>
        <Plus size={16} />
        {t('newChat')}
      </button>

      <div className="search">
        <Search size={15} />
        <input dir="auto" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('searchChats')} />
      </div>

      <nav className="history" aria-label={t('history')}>
        {conversations.length === 0 && <div className="empty-note"><Mascot mood={search ? 'surprised' : 'sleepy'} size={72} /><p>{search ? t('noResults') : t('noChatsYet')}</p></div>}
        {['today', 'yesterday', 'week', 'older'].map(
          (g) =>
            groups[g].length > 0 && (
              <section key={g}>
                <h3>{t('group_' + g)}</h3>
                {groups[g].map((c) => (
                  <div key={c.id} className={`conv${c.id === activeId && view === 'chat' ? ' active' : ''}`}>
                    {editing === c.id ? (
                      <input
                        autoFocus
                        dir="auto"
                        className="conv-edit"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => commit(c.id)}
                        onKeyDown={(e) => { if (e.key === 'Enter') commit(c.id); if (e.key === 'Escape') setEditing(null) }}
                      />
                    ) : (
                      <>
                        <button className="conv-title" dir="auto" onClick={() => onSelect(c.id)} title={c.title}>
                          {c.title || t('untitled')}
                        </button>
                        <span className="conv-actions">
                          <button className="icon-btn small" aria-label={t('rename')} onClick={() => { setEditing(c.id); setDraft(c.title) }}><Pencil size={13} /></button>
                          <button className="icon-btn small" aria-label={t('delete')} onClick={() => onDelete(c.id)}><Trash2 size={13} /></button>
                        </span>
                      </>
                    )}
                  </div>
                ))}
              </section>
            ),
        )}
      </nav>

      <button className={`side-link${view === 'catalog' ? ' active' : ''}`} onClick={onCatalog}>
        <MascotIcon name="catalog" size={22} />
        {t('catalogLink')}
      </button>

      <footer className="account">
        <div className="avatar" aria-hidden="true">{initial}</div>
        <div className="account-name" dir="auto">{name}</div>
        <button className="icon-btn lang-btn" onClick={onToggleLang} aria-label={lang === 'fa' ? 'English' : 'فارسی'} title={lang === 'fa' ? 'English' : 'فارسی'}>
          <Languages size={17} /><span>{lang === 'fa' ? 'EN' : 'فا'}</span>
        </button>
        <button className="icon-btn" onClick={() => onSettings()} aria-label={t('settings')} title={t('settings')}>
          <MascotIcon name="settings" size={24} />
        </button>
      </footer>
    </aside>
  )
}
