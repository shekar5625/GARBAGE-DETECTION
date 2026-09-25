import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'

const TABS = [
  { to: '/pending', label: 'Pending' },
  { to: '/verified', label: 'Verified' },
  { to: '/deleted', label: 'Deleted' },
  { to: '/history', label: 'History' },
]

export function Layout() {
  const { area, signOut } = useAuth()
  const navigate = useNavigate()
  const [pending, setPending] = useState(null)

  // Badge of outstanding detections, refreshed on the same cadence as the tables.
  useEffect(() => {
    if (!area) return
    let alive = true
    const tick = () =>
      api.pendingCount(area).then(
        (n) => alive && setPending(n),
        () => alive && setPending(null)
      )
    tick()
    const id = setInterval(tick, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [area])

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="dot" />
          Garbage Detection
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => (isActive ? 'tab on' : 'tab')}>
              {t.label}
              {t.to === '/pending' && pending > 0 && <span className="badge">{pending}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <span className="dim">{area}</span>
          <button
            className="btn ghost"
            onClick={() => {
              signOut()
              navigate('/login', { replace: true })
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
