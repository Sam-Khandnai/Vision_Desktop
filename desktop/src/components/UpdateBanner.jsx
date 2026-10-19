import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useApp } from '../ctx'
import Mascot from './Mascot'

// Appears when the app found a newer version: first a progress bar, then a restart button.
export default function UpdateBanner() {
  const { t } = useApp()
  const [u, setU] = useState(null)

  useEffect(() => {
    const bridge = window.vision
    if (!bridge || !bridge.onUpdate) return undefined
    if (bridge.getUpdate) bridge.getUpdate().then((s) => s && setU(s)).catch(() => {})
    return bridge.onUpdate(setU)
  }, [])

  if (!u || (u.state !== 'downloading' && u.state !== 'ready')) return null
  const ready = u.state === 'ready'
  return (
    <div className="update-banner" role="status">
      <Mascot mood={ready ? 'happy' : 'thinking'} size={46} blink />
      <div className="update-text" dir="auto">
        <strong>{ready ? t('updateReady', { v: u.version }) : t('updateDownloading', { v: u.version || '' })}</strong>
        {!ready && <div className="update-bar"><span style={{ width: `${u.percent || 0}%` }} /></div>}
      </div>
      {ready && (
        <button className="btn primary" onClick={() => window.vision.installUpdate()}>
          <RefreshCw size={14} /> {t('updateRestart')}
        </button>
      )}
    </div>
  )
}
