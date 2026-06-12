import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queryClient'
import './index.css'
import App from './App.tsx'
import UploadPage from './pages/UploadPage.tsx'
import RunPage from './pages/RunPage.tsx'
import EvalPage from './pages/EvalPage.tsx'

const router = createBrowserRouter([
  { path: '/', element: <UploadPage /> },
  { path: '/runs/:id', element: <RunPage /> },
  { path: '/eval', element: <EvalPage /> },
  { path: '/health', element: <App /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
