import type { ReactNode } from 'react'
import Forbidden from './Forbidden'
import RequireAuth from './RequireAuth'
import { useAuth } from './context'

interface RequirePermissionProps {
  permission: string
  /** `code` que se muestra si la sección se alcanzó pero la API dio `403`. */
  code?: string | null
  children: ReactNode
}

/**
 * Guarda de UI por permiso (task 10.2, design D9).
 *
 * La autorización real es del backend: esto solo evita mostrar acciones que van
 * a fallar. Sin sesión delega en `RequireAuth` (redirige a `/login`), y sin el
 * permiso renderiza `Forbidden` en lugar del contenido.
 */
export default function RequirePermission({
  permission,
  code = null,
  children,
}: RequirePermissionProps) {
  const { status, session, hasPermission } = useAuth()

  if (status !== 'authenticated' || session === null) {
    return <RequireAuth />
  }

  if (!hasPermission(permission)) {
    return <Forbidden code={code} />
  }

  return <>{children}</>
}
