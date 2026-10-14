// Local demo identity: a name and a role, kept in the browser. No real authentication;
// the UI says so. Roles drive the four-eyes flow (analyst proposes, supervisor confirms).
import { createContext, useContext, useState, type ReactNode } from 'react'

export type Role = 'analyst' | 'supervisor'

interface User {
  name: string
  role: Role
  setRole: (role: Role) => void
}

const UserContext = createContext<User | null>(null)

export function UserProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(() => {
    try {
      return (localStorage.getItem('aml.role') as Role) || 'analyst'
    } catch {
      return 'analyst'
    }
  })
  const setRole = (r: Role) => {
    setRoleState(r)
    try {
      localStorage.setItem('aml.role', r)
    } catch {
      // storage unavailable: keep the role for this session only
    }
  }
  const name = role === 'analyst' ? 'analyst.demo' : 'supervisor.demo'
  return <UserContext.Provider value={{ name, role, setRole }}>{children}</UserContext.Provider>
}

export function useUser(): User {
  const ctx = useContext(UserContext)
  if (!ctx) throw new Error('useUser outside UserProvider')
  return ctx
}
