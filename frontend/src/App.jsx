import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBar from './components/InputBar'
import { fetchHealth, fetchHotels, sendChatMessage } from './api'
import './styles/app.css'

let nextId = 1
function makeId() {
  nextId += 1
  return nextId
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [hotels, setHotels] = useState([])
  const [status, setStatus] = useState('offline')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    fetchHealth()
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('offline'))
    fetchHotels()
      .then((data) => setHotels(data.hotels ?? []))
      .catch(() => setHotels([]))
  }, [])

  const handleSend = async (query) => {
    setMessages((prev) => [...prev, { id: makeId(), role: 'user', text: query }])
    setIsLoading(true)
    setSidebarOpen(false)
    try {
      const response = await sendChatMessage(query)
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: 'assistant',
          text: response.answer,
          sourcePages: response.source_pages,
          retrievedHotels: response.retrieved_hotels,
          isFallback: response.is_fallback,
        },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: 'assistant',
          text: `Errore di comunicazione con il server: ${error.message}`,
          isFallback: true,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        status={status}
        hotels={hotels}
        onQuickQuery={handleSend}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <main className="main-panel">
        <ChatArea messages={messages} isLoading={isLoading} onSuggestion={handleSend} />
        <InputBar onSend={handleSend} disabled={isLoading} onToggleSidebar={() => setSidebarOpen((v) => !v)} />
      </main>
    </div>
  )
}
