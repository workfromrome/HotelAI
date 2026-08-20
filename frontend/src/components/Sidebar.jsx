import { useRef, useState } from 'react'
import { TEST_QUERY_TEXT } from '../utils'

function CollapsibleSection({ title, defaultOpen = true, grow = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`sidebar__section ${grow && open ? 'sidebar__section--grow' : ''}`}>
      <button
        type="button"
        className="sidebar__section-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="sidebar__section-title">{title}</span>
        <span className={`sidebar__section-chevron ${open ? 'sidebar__section-chevron--open' : ''}`} aria-hidden="true">
          ▾
        </span>
      </button>
      {open && <div className="sidebar__section-body">{children}</div>}
    </section>
  )
}

const QUICK_QUERIES = [
  'Cerco una struttura pet-friendly vicino al mare.',
  'Mostrami soluzioni con pensione completa e piscina.',
  'Quali strutture sono più adatte a una famiglia con bambini?',
  'Cerco una struttura con spa o centro benessere.',
  'Trova strutture con camere family e parcheggio.',
]

function StatusDot({ status }) {
  const label =
    status === 'ok'
      ? 'Assistente disponibile'
      : status === 'degraded'
        ? 'Assistente con rallentamenti'
        : 'Assistente non disponibile'
  const className =
    status === 'ok'
      ? 'status-dot status-dot--online'
      : status === 'degraded'
        ? 'status-dot status-dot--degraded'
        : 'status-dot status-dot--offline'
  return (
    <span className="status-indicator" title={label}>
      <span className={className} />
      {label}
    </span>
  )
}

function HotelAccordionItem({ hotel }) {
  return (
    <details className="hotel-item">
      <summary>
        <span className="hotel-item__icon" aria-hidden="true">
          🏨
        </span>
        <span className="hotel-item__text">
          <span className="hotel-item__name">{hotel.nome}</span>
          <span className="hotel-item__locality">{hotel.localita}</span>
        </span>
      </summary>
      <div className="hotel-item__body">
        {hotel.stelle && <p className="hotel-item__stars">{hotel.stelle}</p>}
        {hotel.trattamento_principale && <p>Trattamento: {hotel.trattamento_principale}</p>}
        {hotel.caratteristiche_chiave?.length > 0 && (
          <p className="hotel-item__features">{hotel.caratteristiche_chiave.join(' · ')}</p>
        )}
      </div>
    </details>
  )
}

function PdfUploader({ onUploadPdf }) {
  const fileInputRef = useRef(null)
  const [isUploading, setIsUploading] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const handleFileChange = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setIsUploading(true)
    setFeedback(null)
    try {
      const result = await onUploadPdf(file)
      setFeedback(
        result.warning
          ? { type: 'warning', text: result.warning }
          : { type: 'success', text: `Catalogo aggiornato: ${result.count} strutture caricate.` },
      )
    } catch (error) {
      setFeedback({ type: 'error', text: `Impossibile elaborare il PDF: ${error.message}` })
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <section className="sidebar__section">
      <h2 className="sidebar__section-title">Aggiorna catalogo</h2>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        onChange={handleFileChange}
        disabled={isUploading}
        className="pdf-upload-input"
        id="pdf-upload-input"
      />
      <label htmlFor="pdf-upload-input" className={`pdf-upload-btn ${isUploading ? 'pdf-upload-btn--busy' : ''}`}>
        {isUploading ? 'Elaborazione in corso…' : 'Carica un PDF'}
      </label>
      {feedback && (
        <p className={`pdf-upload-feedback pdf-upload-feedback--${feedback.type}`}>
          <span className="pdf-upload-feedback__text">{feedback.text}</span>
          <button
            type="button"
            className="pdf-upload-feedback__close"
            aria-label="Chiudi messaggio"
            onClick={() => setFeedback(null)}
          >
            ×
          </button>
        </p>
      )}
    </section>
  )
}

export default function Sidebar({ status, hotels, onQuickQuery, onUploadPdf, onNewChat, newChatDisabled, isOpen, onClose }) {
  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}
      <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__header">
          <div className="sidebar__brand">
            <span className="sidebar__mark" aria-hidden="true">
              ✦
            </span>
            <div className="sidebar__brand-text">
              <h1 className="sidebar__title">Concierge Hotel</h1>
              <p className="sidebar__tagline">Il tuo assistente per il soggiorno</p>
            </div>
          </div>
          <StatusDot status={status} />
        </div>

        <button type="button" className="new-chat-btn" onClick={onNewChat} disabled={newChatDisabled}>
          <span className="new-chat-btn__icon" aria-hidden="true">
            +
          </span>
          Nuova chat
        </button>

        <CollapsibleSection title="Idee per iniziare">
          <div className="quick-queries">
            {QUICK_QUERIES.map((query) => (
              <button key={query} type="button" className="quick-query-btn" onClick={() => onQuickQuery(query)}>
                {query}
              </button>
            ))}
            <button
              type="button"
              className="quick-query-btn quick-query-btn--test"
              onClick={() => onQuickQuery(TEST_QUERY_TEXT)}
            >
              🧪 {TEST_QUERY_TEXT}
            </button>
          </div>
        </CollapsibleSection>

        <PdfUploader onUploadPdf={onUploadPdf} />

        <CollapsibleSection title={`Strutture disponibili (${hotels.length})`} grow defaultOpen={false}>
          <div className="hotel-list">
            {hotels.map((hotel) => (
              <HotelAccordionItem key={hotel.id ?? hotel.nome} hotel={hotel} />
            ))}
          </div>
        </CollapsibleSection>
      </aside>
    </>
  )
}
