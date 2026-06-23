'use client'
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { insforge } from './insforge'

interface AuthUser {
  id: string
  email?: string
  [k: string]: unknown
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  refresh: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  refresh: async () => {},
  signOut: async () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const { data, error } = await insforge.auth.getCurrentUser()
    setUser(error ? null : ((data?.user as AuthUser) ?? null))
    setLoading(false)
  }, [])

  const signOut = useCallback(async () => {
    await insforge.auth.signOut()
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data, error } = await insforge.auth.getCurrentUser()
      let u = error ? null : ((data?.user as AuthUser) ?? null)
      // Demo mode: if nobody is signed in, auto-sign-in the shared demo account so
      // visitors (judges) land straight in the composer — no sign-up friction. The
      // login page stays available for real accounts.
      const demoEmail = process.env.NEXT_PUBLIC_DEMO_EMAIL
      const demoPw = process.env.NEXT_PUBLIC_DEMO_PASSWORD
      if (!u && demoEmail && demoPw) {
        const r = await insforge.auth.signInWithPassword({ email: demoEmail, password: demoPw })
        if (!r.error) {
          const re = await insforge.auth.getCurrentUser()
          u = re.error ? null : ((re.data?.user as AuthUser) ?? null)
        }
      }
      if (cancelled) return
      setUser(u)
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, refresh, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
