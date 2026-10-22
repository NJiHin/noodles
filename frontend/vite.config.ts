import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const api = process.env.NOODLES_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(['/courses', '/versions', '/files', '/runs', '/progress'].map((p) => [p, api])),
  },
})
