import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { clearSession, loadSession, saveSession } from './api/session'
import TopBar from './components/TopBar'
import LoginPage from './pages/LoginPage'
import CaseQueuePage from './pages/CaseQueuePage'
import NewCasePage from './pages/NewCasePage'
import CaseWorkspacePage from './pages/CaseWorkspacePage'
import AdminPrecedentsPage from './pages/AdminPrecedentsPage'
import './App.css'

const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

function Shell({ role, children }) {
  const { session, signOut } = useSession()
  if (!session) return <Navigate to="/login" replace />
  if (session.user.role !== role) {
    return <Navigate to={session.user.role === 'admin' ? '/admin/precedents' : '/'} replace />
  }
  return (
    <>
      <TopBar user={session.user} onSignOut={signOut} />
      <main className="page">{children}</main>
    </>
  )
}

function Routing() {
  const { session } = useSession()
  return (
    <Routes>
      <Route path="/login" element={session ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route
        path="/"
        element={
          session?.user.role === 'admin' ? (
            <Navigate to="/admin/precedents" replace />
          ) : (
            <Shell role="officer">
              <CaseQueuePage />
            </Shell>
          )
        }
      />
      <Route
        path="/cases/new"
        element={
          <Shell role="officer">
            <NewCasePage />
          </Shell>
        }
      />
      <Route
        path="/cases/:id"
        element={
          <Shell role="officer">
            <CaseWorkspacePage />
          </Shell>
        }
      />
      <Route
        path="/admin/precedents"
        element={
          <Shell role="admin">
            <AdminPrecedentsPage />
          </Shell>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function SessionProvider({ children }) {
  const [session, setSession] = useState(loadSession)
  const navigate = useNavigate()

  const signIn = useCallback((res) => {
    const next = { token: res.access_token, user: res.user }
    saveSession(next)
    setSession(next)
  }, [])
  const signOut = useCallback(() => {
    clearSession()
    setSession(null)
    navigate('/login')
  }, [navigate])

  useEffect(() => {
    const expired = () => {
      setSession(null)
      navigate('/login')
    }
    window.addEventListener('lc:signed-out', expired)
    return () => window.removeEventListener('lc:signed-out', expired)
  }, [navigate])

  const value = useMemo(() => ({ session, signIn, signOut }), [session, signIn, signOut])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <Routing />
      </SessionProvider>
    </BrowserRouter>
  )
}
