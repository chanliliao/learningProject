/**
 * App — root component rendered at `/health`.
 *
 * Shows live connectivity status for all four backend services: the API server,
 * Postgres, Qdrant, and the LLM endpoint.  Each service is polled independently
 * via React Query so one slow check does not block the others.
 */

import { useQuery } from '@tanstack/react-query'
import { getHealth, getDbHealth, getQdrantHealth, getLlmHealth } from './api'
import NavBar from './components/NavBar'

/** Props for `StatusRow`. */
type StatusRowProps = { label: string; ok: boolean | undefined; loading: boolean }

/**
 * Single-service status row with a coloured indicator dot.
 *
 * @param props.label   - Service display name.
 * @param props.ok      - `true` = healthy, `false` = unhealthy, `undefined` = unknown.
 * @param props.loading - When true, shows `"..."` instead of a check/cross.
 */
function StatusRow({ label, ok, loading }: StatusRowProps) {
  const dot = loading ? '...' : ok ? '✓' : '✗'
  const color = loading ? 'text-gray-400' : ok ? 'text-green-500' : 'text-red-500'
  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-200">
      <span className={`text-lg font-mono ${color}`}>{dot}</span>
      <span className="text-gray-700 font-medium">{label}</span>
    </div>
  )
}

/**
 * Health dashboard component.
 *
 * Route: `/health`
 *
 * Each service query is independent — a failure in one does not affect the others.
 * When the LLM health check succeeds, the model's greeting reply is shown as a
 * sanity-check that the model is responding coherently.
 */
function App() {
  const backend = useQuery({ queryKey: ['health'], queryFn: getHealth })
  const db = useQuery({ queryKey: ['health-db'], queryFn: getDbHealth })
  const qdrant = useQuery({ queryKey: ['health-qdrant'], queryFn: getQdrantHealth })
  const llm = useQuery({ queryKey: ['health-llm'], queryFn: getLlmHealth })

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <div className="flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow p-8 w-full max-w-md">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Pipeline Status</h1>
        <StatusRow label="Backend" ok={backend.data?.status === 'ok'} loading={backend.isLoading} />
        <StatusRow label="Postgres" ok={db.data?.status === 'ok'} loading={db.isLoading} />
        <StatusRow label="Qdrant" ok={qdrant.data?.status === 'ok'} loading={qdrant.isLoading} />
        <StatusRow label="LLM" ok={llm.data?.status === 'ok'} loading={llm.isLoading} />
        {llm.data?.reply && (
          <p className="mt-4 text-sm text-gray-600 italic">&ldquo;{llm.data.reply}&rdquo;</p>
        )}
      </div>
      </div>
    </div>
  )
}

export default App
