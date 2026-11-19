import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { logout } from './api/client'
import {
  clearSession,
  loadSession,
  saveSession,
  sessionFrom,
  setNotice,
  setReturn,
  takeReturn,
} from './api/session'
import { clearDrafts } from './lib/drafts'
import SessionGuard from './components/SessionGuard'
import Sidebar from './components/Sidebar'
import UserMenu from './components/UserMenu'
import ThemeToggle from './components/ThemeToggle'
import NotificationBell from './components/NotificationBell'
import { UnreadProvider } from './components/UnreadProvider'
import AppFooter from './components/AppFooter'
import Loader from './components/Loader'
import { LoadingProvider, Reveal, useBooted } from './components/Loading'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import CaseQueuePage from './pages/CaseQueuePage'
import NewCasePage from './pages/NewCasePage'
import CaseWorkspacePage from './pages/CaseWorkspacePage'
import AdminHomePage from './pages/AdminHomePage'
import AdminPrecedentsPage from './pages/AdminPrecedentsPage'
import AdminUsersPage from './pages/AdminUsersPage'
import AdminAiControlPage from './pages/AdminAiControlPage'
import AdminOfficerPage from './pages/AdminOfficerPage'
import AuditorOverviewPage from './pages/AuditorOverviewPage'
import AuditLogPage from './pages/AuditLogPage'
import AuditorCasesPage from './pages/AuditorCasesPage'
import AuditorUsersPage from './pages/AuditorUsersPage'
import AdminMessagesPage from './pages/AdminMessagesPage'
import HelpPage from './pages/HelpPage'
import ApplicantUploadPage from './pages/ApplicantUploadPage'
import UploadLinksPage from './pages/UploadLinksPage'
import SentItemsPage from './pages/SentItemsPage'
import IssuesPage from './pages/IssuesPage'
import InboxPage from './pages/InboxPage'
import AdminIssuesPage from './pages/AdminIssuesPage'
import './App.css'

const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

// role is one role, an array of roles, or 'any' (every role, e.g. Help)
function Shell({ role, children }) {
  const { session, signOut } = useSession()
  const booted = useBooted()
  const { pathname } = useLocation()
  if (!session) return <Navigate to="/login" replace />
  if (role !== 'any' && ![role].flat().includes(session.user.role)) {
    return <Navigate to="/" replace />
  }
  return (
    <div className={`shell${booted ? '' : ' shell-booting'}`}>
      <Sidebar user={session.user} />
      <div className="page-col">
        <header className="topbar">
          {session.user.role !== 'auditor' && <NotificationBell user={session.user} />}
          <ThemeToggle />
          <UserMenu user={session.user} onSignOut={signOut} />
        </header>
        <Reveal key={pathname}>
          <main className="page">{children}</main>
        </Reveal>
        <AppFooter />
      </div>
      {!booted && (
        <div className="boot-screen">
          <Loader label="Getting your desk ready" />
        </div>
      )}
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
          ) : session?.user.role === 'auditor' ? (
            <Shell role="auditor">
              <AuditorOverviewPage />
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
          <Shell role={['officer', 'admin']}>
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
        path="/admin/ai"
        element={
          <Shell role="admin">
            <AdminAiControlPage />
          </Shell>
        }
      />
      <Route
        path="/admin/users/:id"
        element={
          <Shell role="admin">
            <AdminOfficerPage />
          </Shell>
        }
      />
      <Route path="/u" element={<ApplicantUploadPage />} />
      <Route
        path="/links"
        element={
          <Shell role="officer">
            <UploadLinksPage />
          </Shell>
        }
      />
      <Route
        path="/admin/links"
        element={
          <Shell role="admin">
            <UploadLinksPage />
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
        path="/inbox"
        element={
          <Shell role="officer">
            <InboxPage />
          </Shell>
        }
      />
      <Route
        path="/admin/inbox"
        element={
          <Shell role="admin">
            <InboxPage />
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
        path="/admin/messages"
        element={
          <Shell role="admin">
            <AdminMessagesPage />
          </Shell>
        }
      />
      <Route
        path="/auditor/cases"
        element={
          <Shell role="auditor">
            <AuditorCasesPage />
          </Shell>
        }
      />
      <Route
        path="/auditor/audit-log"
        element={
          <Shell role="auditor">
            <AuditLogPage />
          </Shell>
        }
      />
      <Route
        path="/auditor/users"
        element={
          <Shell role="auditor">
            <AuditorUsersPage />
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

const ENDED_NOTICE = {
  idle: 'You were signed out after 30 minutes of no activity. What you typed is saved.',
  max: 'Your 12-hour working session ended. Sign in again; what you typed is saved.',
}

function SessionProvider({ children }) {
  const [session, setSession] = useState(loadSession)
  const navigate = useNavigate()

  const signIn = useCallback(
    (res) => {
      const next = sessionFrom(res)
      saveSession(next)
      setSession(next)
      // Back to the page they were on, if the same person is signing in again.
      const back = takeReturn(res.user.id)
      if (back) navigate(back, { replace: true })
    },
    [navigate],
  )

  // The session ended on its own (idle, 12 hours, closed by the server): keep their typing and
  // their place, say why on the sign-in page.
  const endSession = useCallback(
    (reason, message) => {
      const who = loadSession()?.user.id
      if (who) setReturn(who, window.location.pathname)
      setNotice(ENDED_NOTICE[reason] || message || 'Your session ended. Sign in again.')
      if (reason === 'idle' || reason === 'max') logout()
      clearSession()
      setSession(null)
      navigate('/login')
    },
    [navigate],
  )

  // Deliberate sign-out: the server session ends and saved drafts are wiped.
  const signOut = useCallback(() => {
    logout()
    clearDrafts()
    clearSession()
    setSession(null)
    navigate('/login')
  }, [navigate])

  useEffect(() => {
    const ended = (e) => {
      setNotice(e.detail?.message || 'Your session ended. Sign in again.')
      if (e.detail?.userId) setReturn(e.detail.userId, window.location.pathname)
      setSession(null)
      navigate('/login')
    }
    window.addEventListener('lc:signed-out', ended)
    return () => window.removeEventListener('lc:signed-out', ended)
  }, [navigate])

  const value = useMemo(() => ({ session, signIn, signOut }), [session, signIn, signOut])
  return (
    <SessionContext.Provider value={value}>
      {children}
      {session && <SessionGuard onEnd={endSession} />}
    </SessionContext.Provider>
  )
}

// The unread count belongs to the signed-in person, so it is read here, beside the session.
function WithUnread({ children }) {
  const { session } = useSession()
  return <UnreadProvider user={session?.user}>{children}</UnreadProvider>
}

export default function App() {
  return (
    <BrowserRouter>
      <LoadingProvider>
        <SessionProvider>
          <WithUnread>
            <Routing />
          </WithUnread>
        </SessionProvider>
      </LoadingProvider>
    </BrowserRouter>
  )
}
