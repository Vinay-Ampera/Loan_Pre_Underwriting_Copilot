// The signed-in user, the short access token and the session limits live in sessionStorage: they
// go when the tab closes. The refresh token is an HttpOnly cookie that scripts cannot read.
const KEY = 'lc.session'
const NOTICE = 'lc.notice'
const RETURN = 'lc.return'

export function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY)) || null
  } catch {
    return null
  }
}

export function saveSession(session) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    /* storage unavailable: the session lasts until reload */
  }
}

export function clearSession() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to clear */
  }
}

/** The stored shape of a login or refresh response. `issuedAt` times the silent renewal. */
export function sessionFrom(res) {
  return { token: res.access_token, user: res.user, info: res.session, issuedAt: Date.now() }
}

/** A line for the sign-in page after the session ended on its own ("signed out after 30 minutes"). */
export function setNotice(message) {
  try {
    sessionStorage.setItem(NOTICE, message)
  } catch {
    /* the notice is a courtesy */
  }
}

export function takeNotice() {
  try {
    const message = sessionStorage.getItem(NOTICE)
    sessionStorage.removeItem(NOTICE)
    return message
  } catch {
    return null
  }
}

/** Where the person was, so the same person lands back there after signing in again. */
export function setReturn(userId, path) {
  try {
    sessionStorage.setItem(RETURN, JSON.stringify({ userId, path }))
  } catch {
    /* the return path is a courtesy */
  }
}

export function takeReturn(userId) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(RETURN))
    sessionStorage.removeItem(RETURN)
    return saved && saved.userId === userId ? saved.path : null
  } catch {
    return null
  }
}
