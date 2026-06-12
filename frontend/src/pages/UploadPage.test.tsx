import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import UploadPage from './UploadPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../api', () => ({
  listTargetSchemas: vi.fn().mockResolvedValue([
    { id: 1, name: 'Schema A', version: '1.0' },
  ]),
  startRun: vi.fn().mockResolvedValue({ run_id: 42, status: 'awaiting_review' }),
}))

import { startRun } from '../api'

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('UploadPage', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    vi.mocked(startRun).mockResolvedValue({ run_id: 42, status: 'awaiting_review' })
  })

  it('renders schema select and file input', async () => {
    wrap(<UploadPage />)
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())
    expect(screen.getByLabelText(/file/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument()
  })

  it('calls startRun and navigates on submit', async () => {
    const user = userEvent.setup()
    wrap(<UploadPage />)

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())

    const file = new File(['<xml/>'], 'test.xml', { type: 'application/xml' })
    const fileInput = screen.getByLabelText(/file/i)
    await user.upload(fileInput, file)

    await user.click(screen.getByRole('button', { name: /start/i }))

    await waitFor(() => expect(startRun).toHaveBeenCalledWith(file, 1))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/runs/42'))
  })
})
