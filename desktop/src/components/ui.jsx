import { useEffect } from 'react'
import { X } from 'lucide-react'
import { hasNativePicker, pickFile, pickFolder } from '../api'
import { useApp } from '../ctx'

export function Modal({ title, onClose, children, wide = false, footer = null }) {
  const { t } = useApp()
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={t('close')}><X size={18} /></button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className={`toggle${checked ? ' on' : ''}`} onClick={() => onChange(!checked)}>
      <span />
    </button>
  )
}

export function Field({ label, help, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {help && <span className="field-help">{help}</span>}
    </label>
  )
}

export function PathInput({ value, onChange, kind = 'folder', placeholder }) {
  const { t } = useApp()
  const browse = async () => {
    const p = kind === 'folder' ? await pickFolder() : await pickFile()
    if (p) onChange(p)
  }
  return (
    <div className="path-input">
      <input dir="ltr" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} spellCheck={false} />
      {hasNativePicker() && <button type="button" className="btn" onClick={browse}>{t('browse')}</button>}
    </div>
  )
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}
