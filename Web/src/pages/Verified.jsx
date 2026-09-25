import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import { useDetections } from '../api/useDetections'
import { DetectionTable } from '../components/DetectionTable'

// is_verified = 1. /verify toggles, so the same call sends a row back to pending.
export function Verified() {
  const { area } = useAuth()
  const { rows, loading, error, reload } = useDetections(api.verified, area)

  return (
    <section>
      <h2>Verified</h2>
      <p className="dim sub">Confirmed garbage detections.</p>
      <DetectionTable
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Nothing verified yet."
        actions={(row) => (
          <button
            className="btn ghost sm"
            onClick={async () => {
              await api.verify(row.id, row.area)
              reload({ quiet: true })
            }}
          >
            Return to pending
          </button>
        )}
      />
    </section>
  )
}
