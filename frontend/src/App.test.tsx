import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

function mockFetch(url: string) {
  if (url.includes('/health/llm')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok', reply: 'hi' }) })
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
}

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.stubGlobal('fetch', (url: string) => mockFetch(url))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows service status rows and llm reply', async () => {
  renderWithQuery(<App />)
  expect(await screen.findByText(/Backend/i)).toBeInTheDocument()
  expect(await screen.findByText(/Postgres/i)).toBeInTheDocument()
  expect(await screen.findByText(/Qdrant/i)).toBeInTheDocument()
  expect(await screen.findByText(/LLM/i)).toBeInTheDocument()
  expect(await screen.findByText(/hi/i)).toBeInTheDocument()
})
