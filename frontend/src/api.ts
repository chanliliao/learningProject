const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json()
}

export const getHealth = () => get<{ status: string }>('/health')
export const getDbHealth = () => get<{ status: string }>('/health/db')
export const getQdrantHealth = () => get<{ status: string }>('/health/qdrant')
export const getLlmHealth = () => get<{ status: string; reply: string }>('/health/llm')
