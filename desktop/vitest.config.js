import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    include: ['src/**/*.test.jsx'],
    env: { VITE_BACKEND: `http://127.0.0.1:${process.env.SMOKE_PORT || 8791}` },
    // same origin the dev UI uses, so the backend's CORS allow-list applies exactly as in development
    environmentOptions: { happyDOM: { url: 'http://localhost:5173' } },
  },
})
