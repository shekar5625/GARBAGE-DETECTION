import { useEffect } from 'react'
import { mediaUrl } from '../api/client'

// Full-size view of one detection image.
export function ImageViewer({ row, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="viewer" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <strong>{row.area}</strong>
            <span className="dim"> · {row.date} {row.time}</span>
          </div>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </header>
        <img src={mediaUrl(row.image)} alt={`Detection at ${row.time}`} />
      </div>
    </div>
  )
}
