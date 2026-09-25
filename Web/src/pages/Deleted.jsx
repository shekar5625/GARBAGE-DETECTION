import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'
import { useDetections } from '../api/useDetections'
import { DetectionTable } from '../components/DetectionTable'

// is_verified = 2. A holding area, not a delete: rows here still exist in the DB
// until purged. /delete_row and /delete_all are the only irreversible calls in
// the app, so both are behind a confirmation.
export function Deleted() {
  const { area, isAdmin } = useAuth()
  const { rows, loading, error, reload } = useDetections(api.deleted, area)
  const [confirmAll, setConfirmAll] = useState(false)

  return (
    <section>
      <div className="section-head">
        <div>
          <h2>Dismissed</h2>
          <p className="dim sub">Restore a row, or delete it permanently.</p>
        </div>
        {isAdmin && rows.length > 0 && (
          <button className="btn danger" onClick={() => setConfirmAll(true)}>
            Empty ({rows.length})
          </button>
        )}
      </div>

      {confirmAll && (
        <div className="notice warn confirm">
          <span>
            Permanently delete all {rows.length} dismissed detections? This cannot be undone.
          </span>
          <div className="row-actions">
            <button
              className="btn danger sm"
              onClick={async () => {
                await api.purgeAll()
                setConfirmAll(false)
                reload({ quiet: true })
              }}
            >
              Delete them
            </button>
            <button className="btn ghost sm" onClick={() => setConfirmAll(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <DetectionTable
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Nothing dismissed."
        actions={(row) => <RowActions row={row} onDone={() => reload({ quiet: true })} />}
      />
    </section>
  )
}

function RowActions({ row, onDone }) {
  const [confirming, setConfirming] = useState(false)

  if (confirming) {
    return (
      <div className="row-actions">
        <button
          className="btn danger sm"
          onClick={async () => {
            await api.purge(row.id)
            onDone()
          }}
        >
          Delete forever
        </button>
        <button className="btn ghost sm" onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="row-actions">
      <button
        className="btn ghost sm"
        onClick={async () => {
          await api.remove(row.id) // toggles 2 -> 0
          onDone()
        }}
      >
        Restore
      </button>
      <button className="btn danger sm" onClick={() => setConfirming(true)}>
        Delete
      </button>
    </div>
  )
}
