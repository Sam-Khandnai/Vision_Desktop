import { useId } from 'react'

/*
  Vision mascot, drawn as vector SVG so it stays sharp at 16px and at 400px,
  uses the theme colour, and can change expression from code.

  <Mascot mood="happy" size={64} blink float status="online" />

  moods:  normal happy veryHappy thinking typing curious surprised sad wink love sleepy
  status: online | offline | error | warning | disabled   (small badge, like the status sheet)
*/
const ACCENT = '#2cc5b4'
const HEART = 'M0 3.2C-5 -0.5 -4.2 -4.6 -1.8 -4.6C-0.7 -4.6 0 -3.9 0 -3.2C0 -3.9 0.7 -4.6 1.8 -4.6C4.2 -4.6 5 -0.5 0 3.2Z'
const EYES = [68, 152]
const EYE_Y = 60

const MOODS = {
  normal:    { pupil: [3, -2], mouth: 'smile' },
  happy:     { pupil: [3, -2], mouth: 'grin' },
  veryHappy: { eyes: 'joy', mouth: 'open' },
  thinking:  { pupil: [6, -7], mouth: 'flat', bubble: true },
  typing:    { pupil: [3, 1], mouth: 'dots' },
  curious:   { pupil: [9, -1], mouth: 'tilt', wide: true },
  surprised: { pupil: [3, -2], mouth: 'o', small: true },
  sad:       { pupil: [0, 4], mouth: 'frown', lids: true, tear: true },
  wink:      { pupil: [3, -2], mouth: 'grin', eyes: 'wink' },
  love:      { pupil: [3, -2], mouth: 'grin', heartEyes: true, floatHeart: true },
  sleepy:    { eyes: 'sleep', mouth: 'rest', zzz: true },
}

const BADGES = {
  online: '#3ddc84',
  error: '#ef6b73',
  warning: '#e6b450',
  offline: '#6b7780',
  disabled: '#6b7780',
}

function Mouth({ kind }) {
  const stroke = { fill: 'none', stroke: ACCENT, strokeWidth: 3.2, strokeLinecap: 'round' }
  switch (kind) {
    case 'grin':  return <path d="M98 90Q110 105 122 90" {...stroke} />
    case 'open':  return <path d="M97 89Q110 114 123 89Z" fill={ACCENT} fillOpacity=".9" stroke={ACCENT} strokeWidth="2.5" strokeLinejoin="round" />
    case 'flat':  return <path d="M103 95H117" {...stroke} />
    case 'tilt':  return <path d="M103 96Q111 90 119 94" {...stroke} />
    case 'o':     return <ellipse cx="110" cy="95" rx="4.6" ry="5.6" {...stroke} />
    case 'frown': return <path d="M100 99Q110 89 120 99" {...stroke} />
    case 'rest':  return <path d="M104 94Q110 98 116 94" {...stroke} />
    case 'dots':
      return (
        <g fill={ACCENT}>
          <circle className="m-dot d1" cx="98" cy="94" r="2.8" />
          <circle className="m-dot d2" cx="110" cy="94" r="2.8" />
          <circle className="m-dot d3" cx="122" cy="94" r="2.8" />
        </g>
      )
    default:      return <path d="M101 92Q110 99 119 92" {...stroke} />
  }
}

function Eye({ cx, side, mood, ids }) {
  const cfg = MOODS[mood]
  const closed = cfg.eyes === 'joy' || cfg.eyes === 'sleep' || (cfg.eyes === 'wink' && side === 'r')
  const arc = { fill: 'none', stroke: ACCENT, strokeWidth: 5.5, strokeLinecap: 'round' }
  if (closed) {
    const d = cfg.eyes === 'sleep'
      ? `M${cx - 20} ${EYE_Y - 2}Q${cx} ${EYE_Y + 14} ${cx + 20} ${EYE_Y - 2}`
      : `M${cx - 22} ${EYE_Y + 6}Q${cx} ${EYE_Y - 20} ${cx + 22} ${EYE_Y + 6}`
    return <path d={d} {...arc} />
  }
  const [px, py] = cfg.pupil || [3, -2]
  const k = cfg.wide ? 1.06 : 1
  const prx = (cfg.small ? 12.5 : 17.5) * k
  const pry = (cfg.small ? 14.5 : 20.5) * k
  const lidY = side === 'l' ? [EYE_Y - 12, EYE_Y - 25] : [EYE_Y - 25, EYE_Y - 12] // outer corner droops
  return (
    <g>
      <g className="eye-open">
        <ellipse cx={cx} cy={EYE_Y} rx={31 * k} ry={34 * k} fill="#040608" stroke={ACCENT} strokeOpacity=".4" strokeWidth="2" />
        <ellipse cx={cx} cy={EYE_Y} rx={25.5 * k} ry={28.5 * k} fill={`url(#${ids.iris})`} />
        {cfg.heartEyes ? (
          <g transform={`translate(${cx + 1} ${EYE_Y + 1}) scale(4.3)`}><path d={HEART} fill="#03070a" /></g>
        ) : (
          <ellipse cx={cx + px} cy={EYE_Y + py} rx={prx} ry={pry} fill="#03070a" />
        )}
        <ellipse cx={cx - 6 + px / 2} cy={EYE_Y - 12 + py / 2} rx="8.2" ry="7.4" fill="#fff" transform={`rotate(-18 ${cx - 6} ${EYE_Y - 12})`} />
        <circle cx={cx + 10 + px / 2} cy={EYE_Y - 4 + py / 2} r="3.2" fill="#fff" />
        {!cfg.heartEyes && <g transform={`translate(${cx + 10 + px / 2} ${EYE_Y + 9 + py / 2})`}><path d={HEART} fill="#fff" /></g>}
        <circle cx={cx - 10} cy={EYE_Y + 17} r="1.7" fill="#fff" fillOpacity=".7" />
        <circle cx={cx - 3} cy={EYE_Y + 19} r="1.4" fill="#fff" fillOpacity=".55" />
        {cfg.lids && (
          <polygon
            points={`${cx - 36},${EYE_Y - 40} ${cx + 36},${EYE_Y - 40} ${cx + 36},${side === 'l' ? lidY[1] : lidY[0]} ${cx - 36},${side === 'l' ? lidY[0] : lidY[1]}`}
            fill="#0a0d10" clipPath={`url(#${ids['clip' + side]})`}
          />
        )}
      </g>
      {cfg.tear && side === 'l' && <path className="m-tear" d={`M${cx - 18} ${EYE_Y + 30}q-4 7 0 10q4 -3 0 -10z`} fill={ACCENT} fillOpacity=".85" />}
    </g>
  )
}

export default function Mascot({ mood = 'normal', size = 64, blink = false, float = false, status, label, className = '' }) {
  const uid = useId().replace(/:/g, '')
  const ids = { iris: `i${uid}`, glow: `g${uid}`, body: `b${uid}`, clipl: `cl${uid}`, clipr: `cr${uid}` }
  const effective = status === 'offline' || status === 'disabled' ? 'sleepy' : mood
  const cfg = MOODS[effective] || MOODS.normal
  const dim = status === 'offline' || status === 'disabled'
  const cls = ['mascot', blink && 'blink', float && 'float', dim && 'dim', className].filter(Boolean).join(' ')
  return (
    <svg className={cls} width={size} height={(size * 140) / 224} viewBox="0 -16 224 140" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <radialGradient id={ids.iris} cx="50%" cy="82%" r="75%">
          <stop offset="0" stopColor="#6ff7ea" />
          <stop offset="1" stopColor="#1fb3a4" />
        </radialGradient>
        <linearGradient id={ids.body} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#141a1e" />
          <stop offset="1" stopColor="#07090b" />
        </linearGradient>
        <filter id={ids.glow} x="-20%" y="-30%" width="140%" height="160%"><feGaussianBlur stdDeviation="5" /></filter>
        {EYES.map((cx, i) => (
          <clipPath key={cx} id={i ? ids.clipr : ids.clipl}><ellipse cx={cx} cy={EYE_Y} rx="31" ry="34" /></clipPath>
        ))}
      </defs>

      <rect x="8" y="8" width="208" height="108" rx="54" fill="none" stroke={ACCENT} strokeOpacity=".55" strokeWidth="5" filter={`url(#${ids.glow})`} />
      <rect x="8" y="8" width="208" height="108" rx="54" fill={`url(#${ids.body})`} stroke={ACCENT} strokeOpacity=".75" strokeWidth="3" />
      <rect x="14" y="14" width="196" height="96" rx="48" fill="none" stroke="#fff" strokeOpacity=".05" strokeWidth="2" />

      <Eye cx={EYES[0] + 2} side="l" mood={effective} ids={ids} />
      <Eye cx={EYES[1] + 2} side="r" mood={effective} ids={ids} />
      <g transform="translate(2 0)"><Mouth kind={cfg.mouth} /></g>

      {cfg.bubble && (
        <g className="m-bubble" fill="none" stroke={ACCENT} strokeOpacity=".85" strokeWidth="2.5">
          <circle cx="206" cy="2" r="3" /><circle cx="214" cy="-7" r="5" />
        </g>
      )}
      {cfg.floatHeart && <g transform="translate(212 -4) scale(2.6)" className="m-bubble"><path d={HEART} fill="#ef6b73" /></g>}
      {cfg.zzz && (
        <g fill={ACCENT} fontFamily="sans-serif" fontWeight="700" className="m-bubble">
          <text x="196" y="6" fontSize="17">z</text><text x="208" y="-6" fontSize="12">z</text>
        </g>
      )}
      {status && BADGES[status] && (
        <g transform="translate(206 104)">
          <circle r="13" fill="#101417" />
          <circle r="9.5" fill={BADGES[status]} />
          {(status === 'error' || status === 'warning') && <g fill="#101417"><rect x="-1.5" y="-5.5" width="3" height="7" rx="1.2" /><circle cy="4.2" r="1.7" /></g>}
        </g>
      )}
    </svg>
  )
}

/* ------------------------------------------------------------------ */
/*  Section icons: the same two eyes, inside a simple outlined shape.   */
/* ------------------------------------------------------------------ */
function gearPath() {
  const pts = []
  for (let i = 0; i < 8; i++) {
    const a = (i * 45 * Math.PI) / 180
    for (const [r, off] of [[16, -17], [21, -9], [21, 9], [16, 17]]) {
      const t = a + (off * Math.PI) / 180
      pts.push(`${(24 + r * Math.sin(t)).toFixed(1)} ${(24 - r * Math.cos(t)).toFixed(1)}`)
    }
  }
  return `M${pts.join('L')}Z`
}
const GEAR = gearPath()
const hexPts = [0, 1, 2, 3, 4, 5].map((i) => {
  const a = (Math.PI / 3) * i
  return `${(24 + 20 * Math.sin(a)).toFixed(1)} ${(24 - 20 * Math.cos(a)).toFixed(1)}`
}).join('L')

const SHAPES = {
  chat:     { shape: <path d="M10 9h28a6 6 0 0 1 6 6v17a6 6 0 0 1-6 6H24l-9 7v-7h-5a6 6 0 0 1-6-6V15a6 6 0 0 1 6-6z" />, eyes: [18, 29, 24] },
  settings: { shape: <path d={GEAR} />, eyes: [19.5, 28.5, 23.5] },
  mcp:      { shape: <g><rect x="6" y="5" width="36" height="12" rx="4" /><rect x="6" y="18" width="36" height="12" rx="4" /><rect x="6" y="31" width="36" height="12" rx="4" /></g>, eyes: [17, 31, 24], dots: true },
  catalog:  { shape: <g><rect x="5" y="7" width="38" height="10" rx="3" /><rect x="7" y="17" width="34" height="25" rx="5" /></g>, eyes: [18, 30, 29] },
  memory:   { shape: <path d={`M${hexPts}Z`} strokeLinejoin="round" />, eyes: [18.5, 29.5, 24] },
  model:    { shape: <g><rect x="11" y="11" width="26" height="26" rx="6" />{[17, 24, 31].map((p) => <path key={p} d={`M${p} 4V11M${p} 37V44M4 ${p}H11M37 ${p}H44`} />)}</g>, eyes: [19.5, 28.5, 24] },
  account:  { shape: <g><circle cx="24" cy="16" r="9.5" /><path d="M6 43c0-9.5 7.5-15 18-15s18 5.5 18 15" /></g>, eyes: [20.5, 27.5, 16], small: true },
}

export function MascotIcon({ name = 'chat', size = 24, className = '' }) {
  const def = SHAPES[name] || SHAPES.chat
  const [lx, rx, y] = def.eyes
  const r = def.small ? 2.1 : 3
  return (
    <svg className={`mascot-icon ${className}`} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <g fill="none" stroke={ACCENT} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">{def.shape}</g>
      {def.dots && <g fill={ACCENT}><circle cx="37" cy="11" r="1.5" /><circle cx="37" cy="37" r="1.5" /></g>}
      {[lx, rx].map((x) => (
        <g key={x}>
          <circle cx={x} cy={y} r={r} fill={ACCENT} />
          <circle cx={x - r * 0.3} cy={y - r * 0.35} r={r * 0.36} fill="#fff" />
        </g>
      ))}
      <path d={`M${(lx + rx) / 2 - 2.6} ${y + r + 3}Q${(lx + rx) / 2} ${y + r + 5.6} ${(lx + rx) / 2 + 2.6} ${y + r + 3}`} fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
