import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '@/api/http'
import {
  changeRole,
  deactivateMember,
  listMembers,
  transferOwnership,
} from '@/api/team'
import type { MemberOut } from '@/api/team'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import { ASSIGNABLE_ROLES, ROLE_LABELS } from './roles'
import type { AssignableRole } from './roles'

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, null, 'Ocurrió un error inesperado.')
}

/**
 * Pantalla de Equipo (task 10.3).
 *
 * La autorización real la hace el backend con `require_permission`; acá solo se
 * ocultan las acciones que la sesión no puede ejecutar. Cada acción muestra el
 * `code` estable del error (por ejemplo `last_owner`) para que la demo y la
 * operación diaria sean diagnósticas sin filtrar detalles internos.
 */
export default function TeamPage() {
  const { hasPermission } = useAuth()
  const [members, setMembers] = useState<MemberOut[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, AssignableRole>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const { members: loaded } = await listMembers()
      setMembers(loaded)
    } catch (error) {
      setListError(asApiError(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const canUpdate = hasPermission('team.update')
  const canDelete = hasPermission('team.delete')
  const canTransfer = hasPermission('ownership.transfer')

  const onSaveRole = async (member: MemberOut) => {
    setActionError(null)
    setNotice(null)
    const rol = drafts[member.id] ?? (member.rol as AssignableRole)
    try {
      const updated = await changeRole(member.id, rol)
      setMembers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setNotice('Rol actualizado.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  const onDeactivate = async (member: MemberOut) => {
    setActionError(null)
    setNotice(null)
    try {
      await deactivateMember(member.id)
      setNotice('Miembro dado de baja.')
      await load()
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  const onTransfer = async (member: MemberOut) => {
    setActionError(null)
    setNotice(null)
    try {
      const { members: updated } = await transferOwnership(member.id, 'clinical_admin')
      setMembers(updated)
      setNotice('Titularidad transferida.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  if (listError !== null && listError.status === 403) {
    return <Forbidden code={listError.code} />
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-4 bg-background p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-foreground">Equipo</h1>
        <Link className="text-sm underline" to="/">
          Volver
        </Link>
      </div>

      {notice ? (
        <Alert>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      ) : null}

      {actionError ? (
        <Alert variant="destructive">
          <AlertDescription>
            <p>{actionError.message}</p>
            {actionError.code ? (
              <p className="mt-1 text-xs">
                Código: <code className="font-mono">{actionError.code}</code>
              </p>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Miembros de la clínica</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p role="status" className="text-sm text-muted-foreground">
              Cargando…
            </p>
          ) : null}
          {!loading && listError !== null ? (
            <p className="text-sm text-destructive">{listError.message}</p>
          ) : null}
          {!loading && members.length === 0 && listError === null ? (
            <p className="text-sm text-muted-foreground">Todavía no hay miembros.</p>
          ) : null}
          {members.length > 0 ? (
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-2 pr-2">
                    Miembro
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Rol
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Estado
                  </th>
                  <th scope="col" className="py-2">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const email = member.email ?? '(sin email)'
                  const isOwner = member.rol === 'owner'
                  return (
                    <tr key={member.id} className="border-b align-middle">
                      <td className="py-2 pr-2">
                        <span className="block font-medium">
                          {member.nombre} {member.apellido}
                        </span>
                        <span className="block text-xs text-muted-foreground">{email}</span>
                      </td>
                      <td className="py-2 pr-2">{member.rol}</td>
                      <td className="py-2 pr-2">{member.activo ? 'Activo' : 'Inactivo'}</td>
                      <td className="flex flex-wrap items-center gap-2 py-2">
                        {canUpdate && !isOwner ? (
                          <>
                            <label className="sr-only" htmlFor={`rol-${member.id}`}>
                              Rol de {email}
                            </label>
                            <select
                              id={`rol-${member.id}`}
                              aria-label={`Rol de ${email}`}
                              className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
                              value={drafts[member.id] ?? (member.rol as AssignableRole)}
                              onChange={(event) =>
                                setDrafts((current) => ({
                                  ...current,
                                  [member.id]: event.target.value as AssignableRole,
                                }))
                              }
                            >
                              {ASSIGNABLE_ROLES.map((role) => (
                                <option key={role} value={role}>
                                  {ROLE_LABELS[role]}
                                </option>
                              ))}
                            </select>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => void onSaveRole(member)}
                            >
                              Guardar rol
                            </Button>
                          </>
                        ) : null}
                        {canDelete && member.activo ? (
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            onClick={() => void onDeactivate(member)}
                          >
                            Dar de baja
                          </Button>
                        ) : null}
                        {canTransfer && member.activo && !isOwner ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void onTransfer(member)}
                          >
                            Transferir titularidad
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
