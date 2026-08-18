import { useState } from 'react'

export default function InputBar({ onSend, disabled, onToggleSidebar }) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
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
      <div className="input-bar">
        <textarea
          className="input-bar__field"
          placeholder="Scrivi la tua richiesta..."
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
