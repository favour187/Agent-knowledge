import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        gutter={8}
        toastOptions={{
          duration: 3000,
          style: {
            background: '#182230',
            color: '#e7ecf2',
            border: '1px solid #263140',
            fontSize: '13px',
            borderRadius: '10px',
            padding: '10px 16px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
          },
          success: {
            iconTheme: {
              primary: '#3fc9b0',
              secondary: '#182230',
            },
          },
          error: {
            iconTheme: {
              primary: '#e5484d',
              secondary: '#182230',
            },
          },
        }}
      />
    </QueryClientProvider>
  </React.StrictMode>
)
