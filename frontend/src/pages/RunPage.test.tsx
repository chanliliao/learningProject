import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RunPage from './RunPage'
import type { RunDetail } from '../api'

const awaitingRun: RunDetail = {
  run: { id: 7, status: 'awaiting_review', source_filename: 'test.xml', created_at: '2026-01-01T00:00:00' },
  stage_results: [
    { id: 1, run_id: 7, stage: 'extract', status: 'approved', payload: {}, created_at: '2026-01-01T00:00:00' },
    { id: 2, run_id: 7, stage: 'map', status: 'awaiting_review', payload: {}, created_at: '2026-01-01T00:00:00' },
  ],
  mappings: [
    { id: 1, run_id: 7, source_path: 'Policy.Num', target_path: 'policyNumber', transform: null, confidence: 0.9, flags: [], status: 'proposed' },
    { id: 2, run_id: 7, source_path: 'Policy.Amt', target_path: 'faceAmount', transform: null, confidence: 0.4, flags: ['type_mismatch'], status: 'proposed' },
  ],
  audit: [],
}


const mockGetRun = vi.fn()
const mockApproveStage = vi.fn().mockResolvedValue({ run_id: 7, status: 'completed' })
const mockRejectStage = vi.fn().mockResolvedValue({ run_id: 7, status: 'failed' })

vi.mock('../api', () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  approveStage: (...args: unknown[]) => mockApproveStage(...args),
  rejectStage: (...args: unknown[]) => mockRejectStage(...args),
  editField: vi.fn().mockResolvedValue({}),
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/runs/7']}>
        <Routes>
          <Route path="/runs/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RunPage', () => {
  beforeEach(() => {
    mockGetRun.mockReset()
    mockApproveStage.mockReset()
    mockApproveStage.mockResolvedValue({ run_id: 7, status: 'completed' })
  })

  it('shows stage timeline with extract approved and map awaiting_review', async () => {
    mockGetRun.mockResolvedValue(awaitingRun)
    wrap(<RunPage />)
    await waitFor(() => expect(screen.getAllByText(/extract/i).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/map/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/awaiting_review/i).length).toBeGreaterThan(0)
  })

  it('shows Approve button and calls approveStage on click', async () => {
    mockGetRun.mockResolvedValue(awaitingRun)
    const user = userEvent.setup()
    wrap(<RunPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /approve/i }))
    await waitFor(() => expect(mockApproveStage).toHaveBeenCalledWith(7, 'map'))
  })
})
