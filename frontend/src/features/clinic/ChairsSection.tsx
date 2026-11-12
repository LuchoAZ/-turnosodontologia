import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { createChair, deactivateChair, listChairs, updateChair } from '@/api/clinic'
import type { ChairOut, ChairTipo } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import { CHAIR_TYPE_OPTIONS, chairTypeLabel } from './catalog'
import { clinicErrorMessage } from './errors'

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, null, 'Ocurrió un error inesperado.')
}

interface ChairDraft {
  nombre: string
  ubicacion: string
}

/**
 * Sección de sillones (tasks 7.1–7.2).
 *
 * La autorización real es del backend (`require_permission`); acá solo se
 * ocultan las acciones sin permiso. La baja es **lógica**: el botón dice "Dar de
 * baja" y la fila queda con `activo: false`.
 */
export default function ChairsSection() {
  const { hasPermission } = useAuth()
  const [chairs, setChairs] = useState<ChairOut[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [nombre, setNombre] = useState('')
  const [tipo, setTipo] = useState<ChairTipo>('consultorio')
  const [ubicacion, setUbicacion] = useState('')
  const [drafts, setDrafts] = useState<Record<string, ChairDraft>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const { chairs: loaded } = await listChairs()
      setChairs(loaded)
    } catch (error) {
      setListError(asApiError(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const canCreate = hasPermission('chair.create')
  const canUpdate = hasPermission('chair.update')
  const canDelete = hasPermission('chair.delete')

  const draftOf = (chair: ChairOut): ChairDraft =>
    drafts[chair.id] ?? { nombre: chair.nombre, ubicacion: chair.ubicacion ?? '' }

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setActionError(null)
    setNotice(null)
    try {
      const created = await createChair({
        nombre,
        tipo,
        ubicacion: ubicacion.trim() === '' ? null : ubicacion,
      })
      setChairs((current) => [...current, created])
      setNombre('')
      setTipo('consultorio')
      setUbicacion('')
      setNotice('Sillón creado.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  const onSave = async (chair: ChairOut) => {
    setActionError(null)
    setNotice(null)
    const draft = draftOf(chair)
    try {
      const updated = await updateChair(chair.id, {
        nombre: draft.nombre,
        ubicacion: draft.ubicacion.trim() === '' ? null : draft.ubicacion,
      })
      setChairs((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setNotice('Sillón actualizado.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  const onDeactivate = async (chair: ChairOut) => {
    setActionError(null)
    setNotice(null)
    try {
      await deactivateChair(chair.id)
      setChairs((current) =>
        current.map((item) => (item.id === chair.id ? { ...item, activo: false } : item)),
      )
      setNotice('Sillón dado de baja.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  if (listError !== null && listError.status === 403) {
    return <Forbidden code={listError.code} />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sillones</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {notice ? (
          <Alert>
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        ) : null}

        {actionError ? (
          <Alert variant="destructive">
            <AlertDescription>
              <p>{clinicErrorMessage(actionError)}</p>
              {actionError.code ? (
                <p className="mt-1 text-xs">
                  Código: <code className="font-mono">{actionError.code}</code>
                </p>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}

        {canCreate ? (
          <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => void onCreate(event)}>
            <div className="flex flex-col gap-1">
              <Label htmlFor="chair-nombre">Nombre del sillón</Label>
              <Input
                id="chair-nombre"
                value={nombre}
                onChange={(event) => setNombre(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="chair-tipo">Tipo de sillón</Label>
              <select
                id="chair-tipo"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                value={tipo}
                onChange={(event) => setTipo(event.target.value as ChairTipo)}
              >
                {CHAIR_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="chair-ubicacion">Ubicación del sillón</Label>
              <Input
                id="chair-ubicacion"
                value={ubicacion}
                onChange={(event) => setUbicacion(event.target.value)}
              />
            </div>
            <Button type="submit">Nuevo sillón</Button>
          </form>
        ) : null}

        {loading ? (
          <p role="status" className="text-sm text-muted-foreground">
            Cargando…
          </p>
        ) : null}
        {!loading && listError !== null ? (
          <p className="text-sm text-destructive">{clinicErrorMessage(listError)}</p>
        ) : null}
        {!loading && chairs.length === 0 && listError === null ? (
          <p className="text-sm text-muted-foreground">Todavía no hay sillones.</p>
        ) : null}

        {chairs.length > 0 ? (
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b">
                <th scope="col" className="py-2 pr-2">
                  Sillón
                </th>
                <th scope="col" className="py-2 pr-2">
                  Tipo
                </th>
                <th scope="col" className="py-2 pr-2">
                  Ubicación
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
              {chairs.map((chair) => {
                const draft = draftOf(chair)
                return (
                  <tr key={chair.id} className="border-b align-middle">
                    <td className="py-2 pr-2">
                      {canUpdate ? (
                        <>
                          <Label className="sr-only" htmlFor={`chair-nombre-${chair.id}`}>
                            Nombre de {chair.nombre}
                          </Label>
                          <Input
                            id={`chair-nombre-${chair.id}`}
                            value={draft.nombre}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [chair.id]: { ...draft, nombre: event.target.value },
                              }))
                            }
                          />
                        </>
                      ) : (
                        chair.nombre
                      )}
                    </td>
                    <td className="py-2 pr-2">{chairTypeLabel(chair.tipo)}</td>
                    <td className="py-2 pr-2">
                      {canUpdate ? (
                        <Input
                          aria-label={`Ubicación de ${chair.nombre}`}
                          value={draft.ubicacion}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [chair.id]: { ...draft, ubicacion: event.target.value },
                            }))
                          }
                        />
                      ) : (
                        (chair.ubicacion ?? '—')
                      )}
                    </td>
                    <td className="py-2 pr-2">{chair.activo ? 'Activo' : 'Inactivo'}</td>
                    <td className="flex flex-wrap items-center gap-2 py-2">
                      {canUpdate ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => void onSave(chair)}
                        >
                          Guardar
                        </Button>
                      ) : null}
                      {canDelete && chair.activo ? (
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => void onDeactivate(chair)}
                        >
                          Dar de baja
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
  )
}
