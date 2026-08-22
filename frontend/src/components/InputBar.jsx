import { useState } from 'react'

export default function InputBar({ onSend, disabled, onToggleSidebar }) {
  const [value, setValue] = useState('')
  const [debugMode, setDebugMode] = useState(false)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, debugMode)
    setValue('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="input-bar-wrapper">
      <button type="button" className="sidebar-toggle" onClick={onToggleSidebar} aria-label="Apri catalogo">
        ☰
      </button>
      <button
        type="button"
        className={`debug-toggle ${debugMode ? 'debug-toggle--active' : ''}`}
        onClick={() => setDebugMode((v) => !v)}
        aria-pressed={debugMode}
        title="Modalità debug: mostra solo i risultati di retrieval, senza chiamare l'LLM"
      >
        🔍
      </button>
      <div className="input-bar">
        <textarea
          className="input-bar__field"
          placeholder={debugMode ? 'Modalità debug: query di retrieval (nessuna chiamata LLM)...' : 'Scrivi la tua richiesta...'}
          value={value}
          rows={1}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          type="button"
          className="input-bar__send"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          aria-label="Invia messaggio"
        >
          ↑
        </button>
      </div>
    </div>
  )
}
