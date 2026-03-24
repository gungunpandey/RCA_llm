import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            // Proxy create-rca and static to FastAPI (Jinja2 pages + assets)
            '/create-rca': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            '/save-rca': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            '/static': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: '../static/spa',
        emptyOutDir: true,
    },
})
