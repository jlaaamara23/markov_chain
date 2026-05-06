// In dev, default to Vite proxy (see vite.config.js). Set VITE_API_URL to override (e.g. production).
const API_BASE =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? '/api' : 'http://127.0.0.1:8001')

export default API_BASE
