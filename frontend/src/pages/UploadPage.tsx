/**
 * UploadPage — document upload form for starting a new pipeline run.
 *
 * Fetches available target schemas from `GET /api/schemas` and lets the user
 * select one, then pick an XML file.  On submit, calls `POST /api/runs` and
 * navigates to the new run's review page.
 */

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { listTargetSchemas, startRun } from '../api'
import NavBar from '../components/NavBar'

/**
 * Upload page component.
 *
 * Route: `/`
 *
 * Controlled form: the schema selector is driven by `schemaId` state (falls back
 * to the first schema returned by the API).  The file input is uncontrolled via a
 * ref to avoid React's synthetic file-input limitations.
 */
export default function UploadPage() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [schemaId, setSchemaId] = useState<number | null>(null)

  const { data: schemas = [] } = useQuery({
    queryKey: ['schemas'],
    queryFn: listTargetSchemas,
  })

  const mutation = useMutation({
    mutationFn: ({ file, id }: { file: File; id: number }) => startRun(file, id),
    onSuccess: (data) => navigate(`/runs/${data.run_id}`),
  })

  /** Validate inputs and fire the mutation when the form is submitted. */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    const id = schemaId ?? schemas[0]?.id
    if (!file || !id) return
    mutation.mutate({ file, id })
  }

  const selectedId = schemaId ?? schemas[0]?.id ?? null

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <div className="flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow p-8 w-full max-w-md">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Upload Document</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="schema-select" className="block text-sm font-medium text-gray-700 mb-1">
              Target Schema
            </label>
            <select
              id="schema-select"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={selectedId ?? ''}
              onChange={(e) => setSchemaId(Number(e.target.value))}
            >
              {schemas.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} v{s.version}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="file-input" className="block text-sm font-medium text-gray-700 mb-1">
              File
            </label>
            <input
              id="file-input"
              type="file"
              accept=".xml"
              ref={fileRef}
              className="w-full text-sm text-gray-600"
            />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full bg-blue-600 text-white rounded-md py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {mutation.isPending ? 'Starting...' : 'Start'}
          </button>
          {mutation.isError && (
            <p className="text-red-500 text-sm">{String(mutation.error)}</p>
          )}
        </form>
      </div>
      </div>
    </div>
  )
}
