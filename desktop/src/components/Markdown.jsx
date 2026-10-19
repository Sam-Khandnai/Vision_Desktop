import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy } from 'lucide-react'
import { openExternal } from '../api'
import { useApp } from '../ctx'

function textOf(node) {
  if (node == null) return ''
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(textOf).join('')
  return textOf(node.props?.children)
}

function CodeBlock({ children }) {
  const { t } = useApp()
  const [done, setDone] = useState(false)
  const code = textOf(children).replace(/\n$/, '')
  const lang = (children?.props?.className || '').replace('language-', '')
  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setDone(true)
    setTimeout(() => setDone(false), 1500)
  }
  return (
    <div className="code-block" dir="ltr">
      <div className="code-head">
        <span>{lang || 'code'}</span>
        <button className="icon-btn small" onClick={copy} aria-label={t('copy')}>
          {done ? <Check size={14} /> : <Copy size={14} />}
          <span>{done ? t('copied') : t('copy')}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

export default function Markdown({ text }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
        a: ({ href, children }) => (
          <a href={href} onClick={(e) => { e.preventDefault(); if (href) openExternal(href) }}>{children}</a>
        ),
        table: ({ children }) => <div className="table-wrap"><table>{children}</table></div>,
      }}
    >
      {text}
    </ReactMarkdown>
  )
}
