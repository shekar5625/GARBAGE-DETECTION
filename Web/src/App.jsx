import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { RequireAuth } from './components/RequireAuth'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { Pending } from './pages/Pending'
import { Verified } from './pages/Verified'
import { Deleted } from './pages/Deleted'
import { History } from './pages/History'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/pending" element={<Pending />} />
            <Route path="/verified" element={<Verified />} />
            <Route path="/deleted" element={<Deleted />} />
            <Route path="/history" element={<History />} />
          </Route>
          <Route path="*" element={<Navigate to="/pending" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
