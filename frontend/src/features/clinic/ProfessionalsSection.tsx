import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createProfessional,
  listProfessionals,
  listSpecialties,
  updateProfessional,
} from '@/api/clinic'
import type { ProfessionalOut, SpecialtyOut } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import { clinicErrorMessage } from './errors'

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, null, 'Ocurrió un error inesperado.')
}

/**
 * Sección de profesionales (task 7.3).
 *
 * El `<select>` de especialidad se llena con `GET /clinic/specialties`: nunca se
 * hardcodea un id del seed, porque un tenant puede tener especialidades propias.
 * La baja es `PATCH activo = false` (`professional.update`); la matriz no tiene
 * `professional.delete`.
 */
export default function ProfessionalsSection() {
  const { hasPermission } = useAuth()
  const [professionals, setProfessionals] = useState<ProfessionalOut[]>([])
  const [specialties, setSpecialties] = useState<SpecialtyOut[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [nombre, setNombre] = useState('')
  const [apellido, setApellido] = useState('')
  const [matricula, setMatricula] = useState('')
  const [especialidadId, setEspecialidadId] = useState('')
  const [duracion, setDuracion] = useState('30')
  const [porcentaje, setPorcentaje] = useState('40')

  const canCreate = hasPermission('professional.create')
  const canUpdate = hasPermission('professional.update')

  const load = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const { professionals: loaded } = await listProfessionals()
      setProfessionals(loaded)
    } catch (error) {
      setListError(asApiError(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!canCreate) return
    let active = true
    listSpecialties()
      .then(({ specialties: loaded }) => {
        if (!active) return
        setSpecialties(loaded)
        setEspecialidadId((current) => current || (loaded[0]?.id ?? ''))
      })
      .catch((error: unknown) => {
        if (active) setActionError(asApiError(error))
      })
    return () => {
      active = false
    }
  }, [canCreate])

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setActionError(null)
    setNotice(null)
    try {
      const created = await createProfessional({
        nombre,
        apellido,
        matricula,
        especialidad_id: especialidadId,
        duracion_default_min: Number(duracion),
        porcentaje_liquidacion: Number(porcentaje),
      })
      setProfessionals((current) => [...current, created])
      setNombre('')
      setApellido('')
      setMatricula('')
      setNotice('Profesional creado.')
    } catch (error) {
      setActionError(asApiError(error))
    }
  }

  const onToggleActivo = async (professional: ProfessionalOut) => {
    setActionError(null)
    setNotice(null)
    try {
      const updated = await updateProfessional(professional.id, { activo: !professional.activo })
      setProfessionals((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setNotice(updated.activo ? 'Profesional reactivado.' : 'Profesional dado de baja.')
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
        <CardTitle>Profesionales</CardTitle>
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
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => void onCreate(event)}
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-nombre">Nombre</Label>
              <Input
                id="professional-nombre"
                value={nombre}
                onChange={(event) => setNombre(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-apellido">Apellido</Label>
              <Input
                id="professional-apellido"
                value={apellido}
                onChange={(event) => setApellido(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-matricula">Matrícula</Label>
              <Input
                id="professional-matricula"
                value={matricula}
                onChange={(event) => setMatricula(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-especialidad">Especialidad</Label>
              <select
                id="professional-especialidad"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                value={especialidadId}
                onChange={(event) => setEspecialidadId(event.target.value)}
                required
              >
                {specialties.map((specialty) => (
                  <option key={specialty.id} value={specialty.id}>
                    {specialty.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-duracion">Duración (min)</Label>
              <Input
                id="professional-duracion"
                type="number"
                min={5}
                max={480}
                value={duracion}
                onChange={(event) => setDuracion(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="professional-porcentaje">Liquidación (%)</Label>
              <Input
                id="professional-porcentaje"
                type="number"
                min={0}
                max={100}
                value={porcentaje}
                onChange={(event) => setPorcentaje(event.target.value)}
              />
            </div>
            <Button type="submit">Nuevo profesional</Button>
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
        {!loading && professionals.length === 0 && listError === null ? (
          <p className="text-sm text-muted-foreground">Todavía no hay profesionales.</p>
        ) : null}

        {professionals.length > 0 ? (
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b">
                <th scope="col" className="py-2 pr-2">
                  Profesional
                </th>
                <th scope="col" className="py-2 pr-2">
                  Matrícula
                </th>
                <th scope="col" className="py-2 pr-2">
                  Especialidad
                </th>
                <th scope="col" className="py-2 pr-2">
                  Duración
                </th>
                <th scope="col" className="py-2 pr-2">
                  Liquidación
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
              {professionals.map((professional) => (
                <tr key={professional.id} className="border-b align-middle">
                  <td className="py-2 pr-2">
                    {professional.nombre} {professional.apellido}
                  </td>
                  <td className="py-2 pr-2">{professional.matricula}</td>
                  <td className="py-2 pr-2">{professional.especialidad.nombre}</td>
                  <td className="py-2 pr-2">{professional.duracion_default_min} min</td>
                  <td className="py-2 pr-2">{Number(professional.porcentaje_liquidacion)}%</td>
                  <td className="py-2 pr-2">{professional.activo ? 'Activo' : 'Inactivo'}</td>
                  <td className="py-2">
                    {canUpdate ? (
                      <Button
                        type="button"
                        variant={professional.activo ? 'destructive' : 'outline'}
                        size="sm"
                        onClick={() => void onToggleActivo(professional)}
                      >
                        {professional.activo ? 'Dar de baja' : 'Reactivar'}
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </CardContent>
    </Card>
  )
}
