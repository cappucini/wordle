import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Settings for the component tests (`npm test`). Kept apart from vite.config.js so the
// app's own build settings stay untouched.
export default defineConfig({
  plugins: [react()],
  test: {
    // a simulated browser page, so components can render without a real browser
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    // every test starts with fresh mocks, so one test's fake answers never leak into the next
    restoreMocks: true,
  },
})
