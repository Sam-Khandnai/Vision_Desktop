// Verifies every t('key') used in the UI exists in both languages. Run: node check-i18n.mjs
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fa, en } from './src/i18n.js'
const files = []
const walk = (d) => readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(join(d, e.name)) : /\.jsx$/.test(e.name) && files.push(join(d, e.name))))
walk('src')
const keys = new Set()
for (const f of files) {
  const src = readFileSync(f, 'utf8')
  for (const m of src.matchAll(/\bt\(\s*'([A-Za-z0-9_]+)'/g)) keys.add(m[1])
  for (const m of src.matchAll(/\bt\(\s*'([A-Za-z0-9_]+_)'\s*\+/g)) keys.add(m[1] + '*')
}
const dyn = { group_: ['today', 'yesterday', 'week', 'older'], tab_: ['account', 'provider', 'mcp'], state_: ['connected', 'connecting', 'idle', 'error', 'disabled'], risk_: ['low', 'medium', 'high'], approval_: ['smart', 'always', 'never'] }
let bad = 0
const need = [...keys].filter((k) => !k.endsWith('*') && !k.endsWith('_'))
for (const [p, vs] of Object.entries(dyn)) vs.forEach((v) => need.push(p + v))
for (const k of ['sugg1', 'sugg2', 'sugg3']) need.push(k)
for (const k of new Set(need)) for (const [n, d] of [['fa', fa], ['en', en]]) if (!(k in d)) { console.log(`MISSING ${n}: ${k}`); bad++ }
for (const k of Object.keys(fa)) if (!(k in en)) { console.log(`en lacks: ${k}`); bad++ }
console.log(bad ? `${bad} problem(s)` : `i18n OK (${new Set(need).size} keys used)`)
process.exit(bad ? 1 : 0)
