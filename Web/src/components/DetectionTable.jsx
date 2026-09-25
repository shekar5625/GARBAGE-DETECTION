import { useState, useMemo } from 'react'
import { mediaUrl } from '../api/client'
import { ImageViewer } from './ImageViewer'

// One table shared by Pending / Verified / Deleted / History. Pages supply the
// rows and whatever action buttons that view allows via `actions`.
export function DetectionTable({ rows, loading, error, actions, emptyText = 'No detections.' }) {
  const [query, setQuery] = useState('')
  const [sortDesc, setSortDesc] = useState(true)
  const [preview, setPreview] = useState(null)

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = q
      ? rows.filter((r) =>
          [r.area, r.date, r.time, r.mac, r.image].some((f) =>
            String(f ?? '').toLowerCase().includes(q)
          )
        )
      : rows
    // Sort newest-first by default. date + time sort lexicographically because
    // the API stores them as YYYY-MM-DD and HH:MM:SS.
    return [...filtered].sort((a, b) => {
      const av = `${a.date} ${a.time}`
      const bv = `${b.date} ${b.time}`
      return sortDesc ? bv.localeCompare(av) : av.localeCompare(bv)
    })
  }, [rows, query, sortDesc])

  return (
    <>
      <div className="toolbar">
        <input
          className="search"
          type="search"
          placeholder="Search area, date, time, MAC…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn ghost" onClick={() => setSortDesc((s) => !s)}>
          {sortDesc ? 'Newest first' : 'Oldest first'}
        </button>
        <span className="count">
          {visible.length} of {rows.length}
        </span>
      </div>

      {error && <p className="notice error">Could not reach the API — {error}</p>}

      <div className="table-wrap">
        <table className="detections">
          <thead>
            <tr>
              <th>Image</th>
              <th>Date</th>
              <th>Time</th>
              <th>Area</th>
              <th>MAC address</th>
              {actions && <th className="actions-col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <td>
                  <button
                    className="thumb"
                    onClick={() => setPreview(row)}
                    title="View full image"
                  >
                    <img src={mediaUrl(row.image)} alt={`Detection at ${row.time}`} loading="lazy" />
                  </button>
                </td>
                <td>{row.date}</td>
                <td className="mono">{row.time}</td>
                <td>{row.area}</td>
                <td className="mono dim">{row.mac}</td>
                {actions && <td className="actions-col">{actions(row)}</td>}
              </tr>
            ))}
            {!visible.length && (
              <tr>
                <td className="empty" colSpan={actions ? 6 : 5}>
                  {loading ? 'Loading…' : query ? 'Nothing matches that search.' : emptyText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {preview && <ImageViewer row={preview} onClose={() => setPreview(null)} />}
    </>
  )
}
