import { createContext, useContext, useState, useCallback } from 'react'

// The logged-in username doubles as the AREA used to scope every query.
// 'admin' is the superuser area: the backend returns all areas for it.
// This replaces the old frontend's 12-branch if/else over hardcoded area names.

const AuthContext = createContext(null)
const STORAGE_KEY = 'gd.user'

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStored)

  const signIn = useCallback((u) => {
    setUser(u)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(u))
    } catch {
      // Private mode / blocked storage: session still works, just not persisted.
    }
  }, [])

  const signOut = useCallback(() => {
    setUser(null)
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
  }, [])

  const area = user?.username ?? null
  return (
    <AuthContext value={{ user, area, isAdmin: area === 'admin', signIn, signOut }}>
      {children}
    </AuthContext>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
