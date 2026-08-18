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
  const className = status === 'ok' ? 'status-dot status-dot--online' : 'status-dot status-dot--offline'
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

export default function Sidebar({ status, hotels, onQuickQuery, isOpen, onClose }) {
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

        <section className="sidebar__section">
          <h2 className="sidebar__section-title">Idee per iniziare</h2>
          <div className="quick-queries">
            {QUICK_QUERIES.map((query) => (
              <button key={query} type="button" className="quick-query-btn" onClick={() => onQuickQuery(query)}>
                {query}
              </button>
            ))}
          </div>
        </section>

        <section className="sidebar__section sidebar__section--grow">
          <h2 className="sidebar__section-title">Strutture disponibili ({hotels.length})</h2>
          <div className="hotel-list">
            {hotels.map((hotel) => (
              <HotelAccordionItem key={hotel.id ?? hotel.nome} hotel={hotel} />
            ))}
          </div>
        </section>
      </aside>
    </>
  )
}
