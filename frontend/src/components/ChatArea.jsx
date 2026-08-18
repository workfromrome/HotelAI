import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatPageRanges, stripPageCitations } from '../utils'

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
      {ranges.map((range) => (
        <span key={range} className="page-badge">
          Pag. {range}
        </span>
      ))}
    </div>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
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
          <div className="message-text message-text--markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripPageCitations(message.text)}</ReactMarkdown>
          </div>
        )}
        {!isUser && message.retrievedHotels?.length > 0 && (
          <p className="message-hotels">Strutture citate: {message.retrievedHotels.join(', ')}</p>
        )}
        {!isUser && <PageBadges pages={message.sourcePages} />}
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  if (messages.length === 0 && !isLoading) {
    return <HeroView onSuggestion={onSuggestion} />
  }

  return (
    <div className="chat-area">
      <div className="chat-scroll">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
