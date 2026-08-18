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
