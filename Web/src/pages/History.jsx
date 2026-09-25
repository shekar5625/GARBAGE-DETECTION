import { useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import { useDetections } from '../api/useDetections'
import { DetectionTable } from '../components/DetectionTable'

const LABELS = { 0: 'Pending', 1: 'Verified', 2: 'Dismissed' }

// Every row regardless of state, with a summary across the three states.
export function History() {
  const { area } = useAuth()
  const { rows, loading, error } = useDetections(api.history, area, { pollMs: 15000 })

  const stats = useMemo(() => {
    const by = { 0: 0, 1: 0, 2: 0 }
    rows.forEach((r) => {
      by[r.status] = (by[r.status] ?? 0) + 1
    })
    return by
  }, [rows])

  return (
    <section>
      <h2>History</h2>
      <p className="dim sub">Every detection recorded{area === 'admin' ? '' : ` for ${area}`}.</p>

      <div className="stats">
        <Stat label="Total" value={rows.length} />
        <Stat label="Pending" value={stats[0]} />
        <Stat label="Verified" value={stats[1]} />
        <Stat label="Dismissed" value={stats[2]} />
      </div>

      <DetectionTable
        rows={rows}
        loading={loading}
        error={error}
        emptyText="No detections recorded yet."
        actions={(row) => (
          <span className={`pill s${row.status}`}>{LABELS[row.status] ?? row.status}</span>
        )}
      />
    </section>
  )
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
