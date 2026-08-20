import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatPageRanges, stripPageCitations } from '../utils'

const TYPEWRITER_CHARS_PER_TICK = 3
const TYPEWRITER_INTERVAL_MS = 10

/** Reveals `text` a few characters at a time, chatgpt-style, instead of all at once. */
function useTypewriter(text, onTick) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!text) {
      setCount(0)
      return undefined
    }
    let current = 0
    setCount(0)
    const id = setInterval(() => {
      current = Math.min(current + TYPEWRITER_CHARS_PER_TICK, text.length)
      setCount(current)
      if (current >= text.length) clearInterval(id)
    }, TYPEWRITER_INTERVAL_MS)
    return () => clearInterval(id)
  }, [text])

  useEffect(() => {
    onTick?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count])

  const isDone = !text || count >= text.length
  return [text ? text.slice(0, count) : '', isDone]
}

const SUGGESTIONS = [
  'Cerco una struttura pet-friendly vicino al mare.',
  'Mostrami soluzioni con pensione completa e piscina.',
  'Cerco una struttura con spa o centro benessere.',
]

function HeroView({ onSuggestion }) {
  return (
    <div className="hero">
      <div className="hero-card">
        <span className="hero-mark" aria-hidden="true">
          ✦
        </span>
        <h2>Ciao, sono il tuo concierge digitale</h2>
        <p>
          Raccontami cosa cerchi — trattamento, servizi, vicinanza al mare, spa, pet-friendly — e ti aiuto a
          trovare la struttura giusta tra quelle in catalogo. Ogni risposta cita le pagine sorgente del documento.
        </p>
        <div className="hero-suggestions">
          {SUGGESTIONS.map((query) => (
            <button key={query} type="button" className="suggestion-chip" onClick={() => onSuggestion(query)}>
              {query}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function PageBadges({ pages }) {
  const ranges = formatPageRanges(pages)
  if (ranges.length === 0) return null
  return (
    <div className="page-badges">
      <span className="page-badges-label">Fonti:</span>
      {ranges.map((range) => (
        <span key={range} className="page-badge">
          Pag. {range}
        </span>
      ))}
    </div>
  )
}

function MessageBubble({ message, onReveal }) {
  const isUser = message.role === 'user'
  const markdownSource = isUser ? '' : stripPageCitations(message.text)
  const [revealedText, isDone] = useTypewriter(markdownSource, onReveal)
  const bubbleClass = [
    'message-bubble',
    isUser ? 'message-bubble--user' : 'message-bubble--assistant',
    !isUser && message.isFallback ? 'message-bubble--fallback' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : ''}`}>
      {!isUser && (
        <span className="message-avatar" aria-hidden="true">
          ✦
        </span>
      )}
      <div className={bubbleClass}>
        {isUser ? (
          <p className="message-text">{message.text}</p>
        ) : (
          <div className={`message-text message-text--markdown ${isDone ? '' : 'message-text--typing'}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{revealedText}</ReactMarkdown>
          </div>
        )}
        {!isUser && !message.isFallback && isDone && <PageBadges pages={message.sourcePages} />}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="message-row">
      <span className="message-avatar" aria-hidden="true">
        ✦
      </span>
      <div className="message-bubble message-bubble--assistant message-bubble--typing">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  )
}

export default function ChatArea({ messages, isLoading, onSuggestion }) {
  const bottomRef = useRef(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleReveal = () => {
    const el = scrollRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (isNearBottom) el.scrollTop = el.scrollHeight
  }

  if (messages.length === 0 && !isLoading) {
    return <HeroView onSuggestion={onSuggestion} />
  }

  return (
    <div className="chat-area">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onReveal={handleReveal} />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
