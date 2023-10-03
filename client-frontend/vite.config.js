/*
 * Copyright (c) 2019-2023 SRI International.
 */

import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vitejs.dev/config/
export default defineConfig({
  root: "src",
  publicDir: "../../prism/client/web/static/",
  plugins: [svelte()],
  server: {
    port: 5000,
    proxy: {
      '/messages': 'http://localhost:7001/',
      '/send': 'http://localhost:7001/',
      '/contacts': 'http://localhost:7001/',
      '/persona': 'http://localhost:7001/'
    }
  },
  build: {
    outDir: '../../prism/client/web/static/',
    target: 'esnext',
  }
})
