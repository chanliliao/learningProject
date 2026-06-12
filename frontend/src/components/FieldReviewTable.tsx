/**
 * FieldReviewTable — editable table of field mappings for the map-stage review gate.
 *
 * When `readonly` is false the reviewer can expand any row into an inline edit
 * form to change the target path or transform, which POSTs to
 * `PATCH /api/runs/{runId}/fields/{fieldId}`.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { FieldMapping } from '../api'
import { editField } from '../api'

/** Props for `FieldReviewTable`. */
type Props = {
  /** ID of the owning pipeline run, used in the edit API call. */
  runId: number
  /** Mapping rows to display. */
  mappings: FieldMapping[]
  /** When true, the "Edit" action column is hidden and no edits can be made. */
  readonly?: boolean
}

/**
 * Red badge displaying a single quality-warning flag string.
 *
 * @param props.flag - Flag label from `FieldMapping.flags`, e.g. `"type_mismatch"`.
 */
function FlagBadge({ flag }: { flag: string }) {
  return (
    <span className="inline-block bg-red-100 text-red-700 text-xs px-1.5 py-0.5 rounded mr-1">
      {flag}
    </span>
  )
}

/**
 * A single row in the field review table.
 *
 * Toggles between a read view and an inline edit form.  When in edit mode,
 * saving calls `PATCH /api/runs/{runId}/fields/{mapping.id}` and invalidates
 * the run query cache so the parent re-renders with updated data.
 *
 * The row has a red background when the mapping has quality flags or a
 * confidence score below 0.8 (matching the backend `confidence_threshold`).
 *
 * @param props.runId   - ID of the owning run.
 * @param props.mapping - The field mapping record for this row.
 * @param props.readonly - When true, hides the edit action column.
 */
function FieldRow({ runId, mapping, readonly }: { runId: number; mapping: FieldMapping; readonly?: boolean }) {
  const [editing, setEditing] = useState(false)
  const [targetPath, setTargetPath] = useState(mapping.target_path)
  const [transform, setTransform] = useState(mapping.transform ?? '')
  const qc = useQueryClient()

  const save = useMutation({
    mutationFn: () => editField(runId, mapping.id, { target_path: targetPath, transform: transform || undefined }),
    onSuccess: () => {
      setEditing(false)
      qc.invalidateQueries({ queryKey: ['run', runId] })
    },
  })

  const isFlagged = mapping.flags.length > 0 || (mapping.confidence !== null && mapping.confidence < 0.8)

  return (
    <tr className={isFlagged ? 'bg-red-50' : ''}>
      <td className="px-3 py-2 text-sm text-gray-700 font-mono">{mapping.source_path}</td>
      <td className="px-3 py-2 text-sm">
        {editing ? (
          <div className="space-y-1">
            <input
              aria-label="target path"
              className="border border-gray-300 rounded px-2 py-1 text-sm w-full"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
            />
            <input
              aria-label="transform"
              className="border border-gray-300 rounded px-2 py-1 text-sm w-full text-gray-500"
              placeholder="transform (optional)"
              value={transform}
              onChange={(e) => setTransform(e.target.value)}
            />
          </div>
        ) : (
          <span className="font-mono">{mapping.target_path}</span>
        )}
      </td>
      <td className="px-3 py-2 text-sm text-gray-600">
        {mapping.confidence !== null ? (mapping.confidence * 100).toFixed(0) + '%' : '—'}
      </td>
      <td className="px-3 py-2 text-sm">
        {mapping.flags.map((f) => <FlagBadge key={f} flag={f} />)}
      </td>
      <td className="px-3 py-2 text-sm">
        <span className="text-xs text-gray-500">{mapping.status}</span>
      </td>
      {!readonly && (
        <td className="px-3 py-2 text-sm">
          {editing ? (
            <div className="flex gap-1">
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending}
                className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
              >
                Save
              </button>
              <button
                onClick={() => setEditing(false)}
                className="text-xs text-gray-500 px-2 py-1 rounded hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-blue-600 hover:underline"
            >
              Edit
            </button>
          )}
        </td>
      )}
    </tr>
  )
}

/**
 * Table of field mappings with optional inline editing.
 *
 * Pass `readonly={true}` after the map gate is approved to prevent further edits.
 *
 * @param props - See `Props` type above.
 */
export default function FieldReviewTable({ runId, mappings, readonly }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th className="px-3 py-2">Source</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Flags</th>
            <th className="px-3 py-2">Status</th>
            {!readonly && <th className="px-3 py-2">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {mappings.map((m) => (
            <FieldRow key={m.id} runId={runId} mapping={m} readonly={readonly} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
