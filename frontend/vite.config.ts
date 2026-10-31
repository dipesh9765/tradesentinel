import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: false,
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/hooks/**', 'src/utils/**', 'src/services/**', 'src/components/**'],
    },
  },
})
