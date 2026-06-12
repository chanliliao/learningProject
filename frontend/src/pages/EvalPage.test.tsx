import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import EvalPage from './EvalPage'
import * as api from '../api'

vi.mock('../api', () => ({
  getEvalReport: vi.fn(),
}))

const mockReport: api.EvalReport = {
  total_records: 5,
  total_proposed: 20,
  total_expected: 18,
  tp: 15, fp: 5, fn: 3,
  precision: 0.75,
  recall: 0.6,
  calibration: [
    { confidence_bucket: 'high (>=0.8)', total: 12, correct: 10, precision: 0.9 },
    { confidence_bucket: 'mid (0.5-0.8)', total: 6, correct: 4, precision: 0.4 },
    { confidence_bucket: 'low (<0.5)', total: 2, correct: 1, precision: 0.2 },
  ],
  total_cost: 0.0025,
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('EvalPage', () => {
  beforeEach(() => {
    vi.mocked(api.getEvalReport).mockResolvedValue(mockReport)
  })

  it('renders precision and recall', async () => {
    renderWithQuery(<EvalPage />)
    expect(await screen.findByText('75.0%')).toBeInTheDocument()
    expect(await screen.findByText('60.0%')).toBeInTheDocument()
  })

  it('renders calibration table rows', async () => {
    renderWithQuery(<EvalPage />)
    expect(await screen.findByText('high (>=0.8)')).toBeInTheDocument()
    expect(await screen.findByText('mid (0.5-0.8)')).toBeInTheDocument()
    expect(await screen.findByText('low (<0.5)')).toBeInTheDocument()
  })

  it('renders total cost', async () => {
    renderWithQuery(<EvalPage />)
    expect(await screen.findByText('$0.0025')).toBeInTheDocument()
  })

  it('shows no-report message when query fails', async () => {
    vi.mocked(api.getEvalReport).mockRejectedValue(new Error('404'))
    renderWithQuery(<EvalPage />)
    expect(await screen.findByText(/No eval report found/)).toBeInTheDocument()
  })
})
