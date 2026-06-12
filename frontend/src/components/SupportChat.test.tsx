import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import SupportChat from './SupportChat'

const mockAskSupport = vi.fn()
const mockApplyProposedEdit = vi.fn().mockResolvedValue({ run_id: 1, status: 'awaiting_review' })

vi.mock('../api', () => ({
  askSupport: (...args: unknown[]) => mockAskSupport(...args),
  applyProposedEdit: (...args: unknown[]) => mockApplyProposedEdit(...args),
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('SupportChat', () => {
  it('submits question and renders answer', async () => {
    mockAskSupport.mockResolvedValue({ answer: 'FaceAmt is the death benefit.', proposed_edits: [] })
    const user = userEvent.setup()
    wrap(<SupportChat runId={1} />)

    const input = screen.getByPlaceholderText(/ask a question/i)
    await user.type(input, 'why is faceAmount mapped?')
    await user.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByText('FaceAmt is the death benefit.')).toBeInTheDocument()
    })
  })

  it('renders proposed edit with Apply button that calls applyProposedEdit', async () => {
    mockAskSupport.mockResolvedValue({
      answer: 'Consider mapping to coverageAmount.',
      proposed_edits: [
        { run_id: 1, field_id: 42, new_target_path: 'coverageAmount', new_transform: null, reason: 'Better match' },
      ],
    })
    const user = userEvent.setup()
    wrap(<SupportChat runId={1} />)

    const input = screen.getByPlaceholderText(/ask a question/i)
    await user.type(input, 'should I remap faceAmount?')
    await user.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      const matches = screen.getAllByText(/coverageAmount/)
      expect(matches.length).toBeGreaterThan(0)
    })

    await user.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() => {
      expect(mockApplyProposedEdit).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ field_id: 42, new_target_path: 'coverageAmount' })
      )
    })
  })
})
