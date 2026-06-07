import { useQuery } from '@tanstack/react-query'
import { getHealth, getDbHealth, getQdrantHealth, getLlmHealth } from './api'

type StatusRowProps = { label: string; ok: boolean | undefined; loading: boolean }

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

function App() {
  const backend = useQuery({ queryKey: ['health'], queryFn: getHealth })
  const db = useQuery({ queryKey: ['health-db'], queryFn: getDbHealth })
  const qdrant = useQuery({ queryKey: ['health-qdrant'], queryFn: getQdrantHealth })
  const llm = useQuery({ queryKey: ['health-llm'], queryFn: getLlmHealth })

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
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
  )
}

export default App
