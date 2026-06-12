import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AuditLog from './AuditLog'
import type { AuditEvent } from '../api'

const events: AuditEvent[] = [
  { id: 1, run_id: 3, actor: 'system', action: 'extract_completed', before: null, after: { count: 5 }, created_at: '2026-01-01T00:00:00' },
  { id: 2, run_id: 3, actor: 'reviewer', action: 'map_approved', before: null, after: { decision: 'approve' }, created_at: '2026-01-01T00:01:00' },
]

describe('AuditLog', () => {
  it('renders rows with actor, action, and timestamp in order', () => {
    render(<AuditLog events={events} />)
    const items = screen.getAllByRole('listitem')
    expect(items.length).toBe(2)
    expect(items[0].textContent).toMatch(/system/)
    expect(items[0].textContent).toMatch(/extract_completed/)
    expect(items[1].textContent).toMatch(/reviewer/)
    expect(items[1].textContent).toMatch(/map_approved/)
  })
})
