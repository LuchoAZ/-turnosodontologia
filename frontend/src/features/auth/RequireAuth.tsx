import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './context'

/** Guarda de rutas: sin sesión no se renderiza nada protegido (design D9). */
export default function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <p role="status" className="text-sm text-muted-foreground">
          Cargando…
        </p>
      </main>
    )
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}
