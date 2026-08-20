const BASE_URL = '/api'

async function request(path, options) {
  const response = await fetch(`${BASE_URL}${path}`, options)
  if (!response.ok) {
    throw new Error(`Richiesta fallita (${response.status})`)
  }
  return response.json()
}

export function sendChatMessage(query, topK = 5) {
  return request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  })
}

export function fetchHotels() {
  return request('/hotels')
}

export function fetchHealth() {
  return request('/health')
}

export async function ingestPdf(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${BASE_URL}/ingest`, { method: 'POST', body: formData })
  if (!response.ok) {
    let detail = `Richiesta fallita (${response.status})`
    try {
      const data = await response.json()
      if (data?.detail) detail = data.detail
    } catch {
      // risposta senza corpo JSON: mantiene il messaggio generico
    }
    throw new Error(detail)
  }
  return response.json()
}
