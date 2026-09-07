import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The GenLayer SDK ships as a prebuilt IIFE bundle (genlayer-sdk.bundle.js)
// exposing window.GenLayerSDK. Copy it verbatim into dist/ and load it
// via a <script> tag in index.html — no bundler processing needed.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist'
  }
})
