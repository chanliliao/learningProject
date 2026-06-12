import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import FieldReviewTable from './FieldReviewTable'
import type { FieldMapping } from '../api'

const mockEditField = vi.fn().mockResolvedValue({})

vi.mock('../api', () => ({
  editField: (...args: unknown[]) => mockEditField(...args),
}))

const mappings: FieldMapping[] = [
  { id: 1, run_id: 5, source_path: 'Policy.Num', target_path: 'policyNumber', transform: null, confidence: 0.9, flags: [], status: 'proposed' },
  { id: 2, run_id: 5, source_path: 'Policy.Amt', target_path: 'faceAmount', transform: null, confidence: 0.4, flags: ['type_mismatch'], status: 'proposed' },
]

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('FieldReviewTable', () => {
  it('renders source, target, confidence, flags columns', () => {
    wrap(<FieldReviewTable runId={5} mappings={mappings} />)
    expect(screen.getByText('Policy.Num')).toBeInTheDocument()
    expect(screen.getByText('policyNumber')).toBeInTheDocument()
    expect(screen.getByText('Policy.Amt')).toBeInTheDocument()
    expect(screen.getByText('faceAmount')).toBeInTheDocument()
    expect(screen.getByText('type_mismatch')).toBeInTheDocument()
  })

  it('calls editField when saving an edited target path', async () => {
    const user = userEvent.setup()
    wrap(<FieldReviewTable runId={5} mappings={mappings} />)

    const editBtns = screen.getAllByRole('button', { name: /edit/i })
    await user.click(editBtns[0])

    const input = screen.getByDisplayValue('policyNumber')
    await user.clear(input)
    await user.type(input, 'newTarget')

    await user.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(mockEditField).toHaveBeenCalledWith(5, 1, expect.objectContaining({ target_path: 'newTarget' })))
  })

  it('highlights flagged rows', () => {
    const { container } = wrap(<FieldReviewTable runId={5} mappings={mappings} />)
    const rows = container.querySelectorAll('tr')
    const flaggedRow = Array.from(rows).find(r => r.textContent?.includes('type_mismatch'))
    expect(flaggedRow).toBeTruthy()
    expect(flaggedRow!.className).toMatch(/red|yellow|flag/i)
  })
})
