/**
 * AuditLog — renders a chronological list of pipeline audit events.
 *
 * Each event shows the timestamp (local time), actor, and action label.
 * Intentionally read-only — no interactions.
 */

import type { AuditEvent } from '../api'

/** Props for `AuditLog`. */
type Props = {
  /** Ordered list of audit events to display (oldest first). */
  events: AuditEvent[]
}

/**
 * Read-only list of audit events for a pipeline run.
 *
 * @param props.events - Array of `AuditEvent` objects from the run detail response.
 */
export default function AuditLog({ events }: Props) {
  return (
    <ul className="space-y-2">
      {events.map((e) => (
        <li key={e.id} className="flex items-start gap-3 text-sm">
          <span className="text-gray-400 font-mono text-xs mt-0.5 w-36 shrink-0">
            {new Date(e.created_at).toLocaleTimeString()}
          </span>
          <span className="font-medium text-gray-700 w-20 shrink-0">{e.actor}</span>
          <span className="text-gray-600">{e.action}</span>
        </li>
      ))}
    </ul>
  )
}
