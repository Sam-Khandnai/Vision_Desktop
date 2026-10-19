import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In production the page is loaded from file:// and may only talk to the local backend.
const csp = {
  name: 'vision-csp',
  apply: 'build',
  transformIndexHtml(html) {
    const policy = [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self' data:",
      "connect-src http://127.0.0.1:* http://localhost:*",
      "object-src 'none'",
      "base-uri 'none'",
    ].join('; ')
    return html.replace('<!--csp-->', `<meta http-equiv="Content-Security-Policy" content="${policy}" />`)
  },
}

export default defineConfig({
  base: './',
  plugins: [react(), csp],
  server: { port: 5173, strictPort: true },
  build: { outDir: 'dist', sourcemap: false },
})
