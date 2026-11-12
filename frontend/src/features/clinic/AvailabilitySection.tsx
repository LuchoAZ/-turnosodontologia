import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createAvailability,
  listAvailability,
  listChairs,
  listProfessionals,
} from '@/api/clinic'
import type { AvailabilityOut, ChairOut, ProfessionalOut } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import { DAY_OPTIONS, dayLabel, hhmm } from './catalog'
import { clinicErrorMessage } from './errors'

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, null, 'Ocurrió un error inesperado.')
}

/**
 * Sección de disponibilidad (task 7.3).
 *
 * La ventana se valida en el backend (`validate_window`) y el solape parcial con
 * otra regla del mismo día devuelve `409 availability_overlap`; la UI no repite
 * esa lógica, solo traduce el `code`.
 */
export default function AvailabilitySection() {
  const { hasPermission } = useAuth()
  const [rules, setRules] = useState<AvailabilityOut[]>([])
  const [professionals, setProfessionals] = useState<ProfessionalOut[]>([])
  const [chairs, setChairs] = useState<ChairOut[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [diaSemana, setDiaSemana] = useState('1')
  const [horaInicio, setHoraInicio] = useState('09:00')
  const [horaFin, setHoraFin] = useState('12:00')
  const [slotMin, setSlotMin] = useState('30')
  const [fechaDesde, setFechaDesde] = useState('')
  const [fechaHasta, setFechaHasta] = useState('')
  const [professionalId, setProfessionalId] = useState('')
  const [chairId, setChairId] = useState('')

  const canUpdate = hasPermission('professional.update')

  const load = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const { availability } = await listAvailability()
      setRules(availability)
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
    if (!canUpdate) return
    let active = true
    Promise.all([listProfessionals(), listChairs()])
      .then(([{ professionals: loadedProfessionals }, { chairs: loadedChairs }]) => {
        if (!active) return
        setProfessionals(loadedProfessionals.filter((item) => item.activo))
        setChairs(loadedChairs.filter((item) => item.activo))
      })
      .catch((error: unknown) => {
        if (active) setActionError(asApiError(error))
      })
    return () => {
      active = false
    }
  }, [canUpdate])

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setActionError(null)
    setNotice(null)
    try {
      const created = await createAvailability({
        dia_semana: Number(diaSemana),
        hora_inicio: horaInicio,
        hora_fin: horaFin,
        slot_min: Number(slotMin),
        fecha_desde: fechaDesde,
        fecha_hasta: fechaHasta.trim() === '' ? null : fechaHasta,
        professional_id: professionalId === '' ? null : professionalId,
        chair_id: chairId === '' ? null : chairId,
      })
      setRules((current) => [...current, created])
      setNotice('Regla de disponibilidad creada.')
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
        <CardTitle>Disponibilidad</CardTitle>
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

        {canUpdate ? (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => void onCreate(event)}
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-dia">Día</Label>
              <select
                id="availability-dia"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                value={diaSemana}
                onChange={(event) => setDiaSemana(event.target.value)}
              >
                {DAY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-inicio">Hora de inicio</Label>
              <Input
                id="availability-inicio"
                type="time"
                value={horaInicio}
                onChange={(event) => setHoraInicio(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-fin">Hora de fin</Label>
              <Input
                id="availability-fin"
                type="time"
                value={horaFin}
                onChange={(event) => setHoraFin(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-slot">Slot (min)</Label>
              <Input
                id="availability-slot"
                type="number"
                min={1}
                value={slotMin}
                onChange={(event) => setSlotMin(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-desde">Vigente desde</Label>
              <Input
                id="availability-desde"
                type="date"
                value={fechaDesde}
                onChange={(event) => setFechaDesde(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-hasta">Vigente hasta</Label>
              <Input
                id="availability-hasta"
                type="date"
                value={fechaHasta}
                onChange={(event) => setFechaHasta(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-profesional">Profesional</Label>
              <select
                id="availability-profesional"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                value={professionalId}
                onChange={(event) => setProfessionalId(event.target.value)}
              >
                <option value="">Toda la clínica</option>
                {professionals.map((professional) => (
                  <option key={professional.id} value={professional.id}>
                    {professional.nombre} {professional.apellido}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="availability-sillon">Sillón</Label>
              <select
                id="availability-sillon"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                value={chairId}
                onChange={(event) => setChairId(event.target.value)}
              >
                <option value="">Cualquier sillón</option>
                {chairs.map((chair) => (
                  <option key={chair.id} value={chair.id}>
                    {chair.nombre}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit">Nueva regla</Button>
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
        {!loading && rules.length === 0 && listError === null ? (
          <p className="text-sm text-muted-foreground">Todavía no hay reglas de disponibilidad.</p>
        ) : null}

        {rules.length > 0 ? (
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b">
                <th scope="col" className="py-2 pr-2">
                  Día
                </th>
                <th scope="col" className="py-2 pr-2">
                  Horario
                </th>
                <th scope="col" className="py-2 pr-2">
                  Slot
                </th>
                <th scope="col" className="py-2 pr-2">
                  Buffers
                </th>
                <th scope="col" className="py-2 pr-2">
                  Vigencia
                </th>
                <th scope="col" className="py-2">
                  Alcance
                </th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id} className="border-b align-middle">
                  <td className="py-2 pr-2">{dayLabel(rule.dia_semana)}</td>
                  <td className="py-2 pr-2">
                    {hhmm(rule.hora_inicio)}–{hhmm(rule.hora_fin)}
                  </td>
                  <td className="py-2 pr-2">{rule.slot_min} min</td>
                  <td className="py-2 pr-2">
                    {rule.buffer_previo_min}/{rule.buffer_posterior_min} min
                  </td>
                  <td className="py-2 pr-2">
                    {rule.fecha_desde}
                    {rule.fecha_hasta ? ` → ${rule.fecha_hasta}` : ' en adelante'}
                  </td>
                  <td className="py-2">
                    {rule.professional_id === null && rule.chair_id === null
                      ? 'Toda la clínica'
                      : [
                          rule.professional_id === null ? null : 'profesional',
                          rule.chair_id === null ? null : 'sillón',
                        ]
                          .filter((part) => part !== null)
                          .join(' + ')}
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
