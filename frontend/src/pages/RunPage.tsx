/**
 * RunPage — per-run review page showing stage timeline, field mappings, and audit log.
 *
 * Polls the backend while the run is `"running"`.  Renders approve/reject buttons
 * when the run is `"awaiting_review"`.  Shows the SupportChat when the run is
 * `"completed"` or `"awaiting_review"`.
 */

import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRun, approveStage, rejectStage } from '../api'
import FieldReviewTable from '../components/FieldReviewTable'
import AuditLog from '../components/AuditLog'
import SupportChat from '../components/SupportChat'
import NavBar from '../components/NavBar'

/** Polling interval in milliseconds while the run is in `"running"` status. */
const POLL_INTERVAL = 2000

/**
 * Run detail page.
 *
 * Route: `/runs/:id`
 *
 * Loads run data via `GET /api/runs/{id}`.  Polls every 2 s while
 * `run.status === "running"` so the UI updates automatically when the pipeline
 * reaches the first review gate.
 *
 * Gate approval/rejection sends `POST /api/runs/{id}/stages/{stage}/approve` or
 * `.../reject`, where `stage` is derived from the first `StageResult` still in
 * `"awaiting_review"` status.  Falls back to `"map"` if no awaiting stage is found.
 */
export default function RunPage() {
  const { id } = useParams<{ id: string }>()
  const runId = Number(id)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status
      return status === 'running' ? POLL_INTERVAL : false
    },
  })

  /** The first stage still awaiting review, used as the target for approve/reject. */
  const pendingStage = data?.stage_results.find(s => s.status === 'awaiting_review')?.stage ?? 'map'

  const [stageError, setStageError] = React.useState<string | null>(null)

  const approve = useMutation({
    mutationFn: () => approveStage(runId, pendingStage),
    onSuccess: () => { setStageError(null); qc.invalidateQueries({ queryKey: ['run', runId] }) },
    onError: (e: Error) => setStageError(e.message),
  })

  const reject = useMutation({
    mutationFn: () => rejectStage(runId, pendingStage),
    onSuccess: () => { setStageError(null); qc.invalidateQueries({ queryKey: ['run', runId] }) },
    onError: (e: Error) => setStageError(e.message),
  })

  if (isLoading || !data) {
    return <div className="p-8 text-gray-500">Loading...</div>
  }

  const { run, stage_results, mappings, audit } = data
  const showReview = run.status === 'awaiting_review'

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <div className="p-8">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Run header: ID, filename, status */}
        <div className="bg-white rounded-xl shadow p-6">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">
            Run #{run.id} — {run.source_filename}
          </h1>
          <p className="text-sm text-gray-500">Status: <span className="font-medium">{run.status}</span></p>
        </div>

        {/* Stage timeline: ordered list of stage results with colour-coded status badges */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-lg font-medium text-gray-800 mb-4">Stage Timeline</h2>
          <div className="space-y-2">
            {stage_results.map((s) => (
              <div key={s.id} className="flex items-center gap-3">
                <span className="text-sm font-mono w-24 text-gray-700">{s.stage}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  s.status === 'approved' ? 'bg-green-100 text-green-700' :
                  s.status === 'awaiting_review' ? 'bg-yellow-100 text-yellow-700' :
                  s.status === 'rejected' ? 'bg-red-100 text-red-700' :
                  'bg-gray-100 text-gray-600'
                }`}>{s.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Field mappings table — shown only once the map stage has produced rows */}
        {mappings.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-lg font-medium text-gray-800 mb-4">Field Mappings</h2>
            <FieldReviewTable runId={runId} mappings={mappings} readonly={!showReview} />
          </div>
        )}

        {/* Inline error message when an approve/reject API call fails */}
        {stageError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            {stageError}
          </div>
        )}

        {/* Approve/reject buttons — visible only while awaiting review */}
        {showReview && (
          <div className="flex gap-3">
            <button
              onClick={() => approve.mutate()}
              disabled={approve.isPending || reject.isPending}
              className="bg-green-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              Approve
            </button>
            <button
              onClick={() => reject.mutate()}
              disabled={approve.isPending || reject.isPending}
              className="bg-red-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        )}

        {/* Support chat — visible for completed runs and during review so users can ask questions at any gate */}
        {(run.status === 'completed' || run.status === 'awaiting_review') && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-lg font-medium text-gray-800 mb-4">Support Assistant</h2>
            <SupportChat runId={runId} />
          </div>
        )}

        {/* Audit log — shown once at least one event exists */}
        {audit.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-lg font-medium text-gray-800 mb-4">Audit Log</h2>
            <AuditLog events={audit} />
          </div>
        )}

      </div>
      </div>
    </div>
  )
}
