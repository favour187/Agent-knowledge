import axios from 'axios'
import { useAuthStore } from '../store/authStore'

// In dev, Vite proxies /api to the FastAPI backend (see vite.config.js).
// In production, set VITE_API_URL to the deployed API's base URL (e.g. https://api.example.com/api).
const baseURL = import.meta.env.VITE_API_URL || '/api'

export const client = axios.create({ baseURL })

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  }
)

/** Extract a readable message from a FastAPI error response. */
export function apiErrorMessage(error, fallback = 'Something went wrong') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
  return error?.message || fallback
}
