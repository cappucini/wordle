// Vite settings for running and building the frontend.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Settings for the dev server and the production build (`npm run dev`, `npm run build`).
// https://vite.dev/config/
export default defineConfig({
  // lets Vite understand JSX, and refresh a component in place when its file is saved
  plugins: [react()],
})
