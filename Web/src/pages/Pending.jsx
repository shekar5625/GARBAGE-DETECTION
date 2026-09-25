import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import { useDetections } from '../api/useDetections'
import { DetectionTable } from '../components/DetectionTable'

// is_verified = 0. The review queue: every new detection from main.py lands here.
export function Pending() {
  const { area } = useAuth()
  const { rows, loading, error, reload } = useDetections(api.pending, area)

  const act = async (fn) => {
    await fn()
    reload({ quiet: true })
  }

  return (
    <section>
      <h2>Pending review</h2>
      <p className="dim sub">New detections awaiting a decision.</p>
      <DetectionTable
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Nothing pending — all caught up."
        actions={(row) => (
          <div className="row-actions">
            <button className="btn primary sm" onClick={() => act(() => api.verify(row.id, row.area))}>
              Verify
            </button>
            <button className="btn danger sm" onClick={() => act(() => api.remove(row.id))}>
              Dismiss
            </button>
          </div>
        )}
      />
    </section>
  )
}
