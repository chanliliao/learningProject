/**
 * EvalPage — offline evaluation dashboard.
 *
 * Displays the latest eval report produced by `uv run python -m eval`.
 * The report is served by `GET /api/eval/latest`.  When no report exists
 * the page shows a helpful command to generate one.
 */

import { useQuery } from '@tanstack/react-query'
import { getEvalReport } from '../api'
import type { CalibrationRow } from '../api'
import NavBar from '../components/NavBar'

/**
 * Single metric display card.
 *
 * @param props.label - Metric name shown in small grey text above the value.
 * @param props.value - Formatted metric value shown in large bold text.
 */
function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl shadow p-6 text-center">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className="text-3xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

/**
 * Confidence-calibration breakdown table.
 *
 * Shows precision per confidence bucket so reviewers can tune the
 * `confidence_threshold` setting.
 *
 * @param props.rows - Calibration rows from the eval report.
 */
function CalibrationTable({ rows }: { rows: CalibrationRow[] }) {
  return (
    <table className="w-full text-left border-collapse text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th className="px-3 py-2">Bucket</th>
          <th className="px-3 py-2">Total</th>
          <th className="px-3 py-2">Correct</th>
          <th className="px-3 py-2">Precision</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.confidence_bucket} className="border-b border-gray-100">
            <td className="px-3 py-2 font-mono text-gray-700">{r.confidence_bucket}</td>
            <td className="px-3 py-2 text-gray-600">{r.total}</td>
            <td className="px-3 py-2 text-gray-600">{r.correct}</td>
            <td className="px-3 py-2 font-medium">{(r.precision * 100).toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Eval dashboard page.
 *
 * Route: `/eval`
 *
 * Fetches the latest eval report with `retry: false` so a missing report
 * immediately shows the "run eval" helper message rather than retrying.
 */
export default function EvalPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['evalReport'],
    queryFn: getEvalReport,
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="p-8 text-gray-500">Loading eval report...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <div className="p-8">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
            No eval report found. Run: <code className="font-mono bg-yellow-100 px-1 rounded">uv run python -m eval</code>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <div className="p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-2xl font-semibold text-gray-900">Eval Dashboard</h1>

        {/* Top-level precision/recall metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard label="Precision" value={`${(data.precision * 100).toFixed(1)}%`} />
          <MetricCard label="Recall" value={`${(data.recall * 100).toFixed(1)}%`} />
          <MetricCard label="Records" value={String(data.total_records)} />
          <MetricCard label="LLM Cost" value={`$${data.total_cost.toFixed(4)}`} />
        </div>

        {/* TP / FP / FN breakdown */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-lg font-medium text-gray-800 mb-2">Mapping Stats</h2>
          <p className="text-sm text-gray-600">
            TP: <span className="font-medium text-green-700">{data.tp}</span>
            {' · '}
            FP: <span className="font-medium text-red-600">{data.fp}</span>
            {' · '}
            FN: <span className="font-medium text-orange-600">{data.fn}</span>
            {' · '}
            Proposed: {data.total_proposed}
            {' · '}
            Expected: {data.total_expected}
          </p>
        </div>

        {/* Per-bucket calibration table */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-lg font-medium text-gray-800 mb-4">Confidence Calibration</h2>
          <CalibrationTable rows={data.calibration} />
        </div>
      </div>
      </div>
    </div>
  )
}
