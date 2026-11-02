import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { clearSession, loadSession, saveSession } from './api/session'
import Sidebar from './components/Sidebar'
import AppFooter from './components/AppFooter'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import CaseQueuePage from './pages/CaseQueuePage'
import NewCasePage from './pages/NewCasePage'
import CaseWorkspacePage from './pages/CaseWorkspacePage'
import AdminHomePage from './pages/AdminHomePage'
import AdminPrecedentsPage from './pages/AdminPrecedentsPage'
import AdminUsersPage from './pages/AdminUsersPage'
import HelpPage from './pages/HelpPage'
import SentItemsPage from './pages/SentItemsPage'
import IssuesPage from './pages/IssuesPage'
import AdminIssuesPage from './pages/AdminIssuesPage'
import './App.css'

const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

// role is 'officer', 'admin' or 'any' (both roles, e.g. Help)
function Shell({ role, children }) {
  const { session, signOut } = useSession()
  if (!session) return <Navigate to="/login" replace />
  if (role !== 'any' && session.user.role !== role) {
    return <Navigate to="/" replace />
  }
  return (
    <div className="shell">
      <Sidebar user={session.user} onSignOut={signOut} />
      <div className="page-col">
        <main className="page">{children}</main>
        <AppFooter />
      </div>
    </div>
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
            <Shell role="admin">
              <AdminHomePage />
            </Shell>
          ) : (
            <Shell role="officer">
              <HomePage />
            </Shell>
          )
        }
      />
      <Route
        path="/cases"
        element={
          <Shell role="officer">
            <CaseQueuePage />
          </Shell>
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
      <Route
        path="/admin/users"
        element={
          <Shell role="admin">
            <AdminUsersPage />
          </Shell>
        }
      />
      <Route
        path="/messages"
        element={
          <Shell role="officer">
            <SentItemsPage />
          </Shell>
        }
      />
      <Route
        path="/problems"
        element={
          <Shell role="officer">
            <IssuesPage />
          </Shell>
        }
      />
      <Route
        path="/admin/issues"
        element={
          <Shell role="admin">
            <AdminIssuesPage />
          </Shell>
        }
      />
      <Route
        path="/help"
        element={
          <Shell role="any">
            <HelpPage />
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
