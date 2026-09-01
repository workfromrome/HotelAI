import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBar from './components/InputBar'
import { fetchHealth, fetchHotels, ingestPdf, sendChatMessage } from './api'
import { TEST_QUERY_TEXT, TEST_RESPONSE_TEXT } from './utils'
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

  const handleSend = async (query, debug = false) => {
    setMessages((prev) => [...prev, { id: makeId(), role: 'user', text: query }])
    setIsLoading(true)
    setSidebarOpen(false)

    if (query === TEST_QUERY_TEXT) {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: 'assistant',
            text: TEST_RESPONSE_TEXT,
            sourcePages: [],
            retrievedHotels: ['Hotel Esempio'],
            isFallback: false,
          },
        ])
        setIsLoading(false)
      }, 500)
      return
    }

    try {
      const response = await sendChatMessage(query, 5, debug)
      const isDebugContext = debug && !response.is_fallback
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: 'assistant',
          text: isDebugContext ? `\`\`\`\n${response.answer}\n\`\`\`` : response.answer,
          sourcePages: response.source_pages,
          retrievedHotels: response.retrieved_hotels,
          isFallback: response.is_fallback,
          isDebug: debug,
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

  const handleNewChat = () => {
    setMessages([])
    setSidebarOpen(false)
  }

  const handleUploadPdf = async (file) => {
    const result = await ingestPdf(file)
    setHotels(result.hotels ?? [])
    fetchHealth()
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('offline'))
    return result
  }

  return (
    <div className="app-shell">
      <Sidebar
        status={status}
        hotels={hotels}
        onQuickQuery={handleSend}
        onUploadPdf={handleUploadPdf}
        onNewChat={handleNewChat}
        disabled={isLoading}
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
