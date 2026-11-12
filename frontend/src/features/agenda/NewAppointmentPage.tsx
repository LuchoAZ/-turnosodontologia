import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { conflictOf, createAppointment, TIPOS_PRACTICA } from '@/api/appointments'
import type { AppointmentOut, TipoPractica } from '@/api/appointments'
import { listChairs, listProfessionals } from '@/api/clinic'
import type { ChairOut, ProfessionalOut } from '@/api/clinic'
import type { ApiError } from '@/api/http'
import { listPatients } from '@/api/patients'
import type { PatientOut } from '@/api/patients'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import { formatInstant, formatRango, localDateTimeToInstant } from './datetime'
import { appointmentErrorMessage, asApiError, recursoLabel } from './errors'

const appointmentSchema = z
  .object({
    professional_id: z.string().min(1, 'Elegí un profesional.'),
    chair_id: z.string().min(1, 'Elegí un sillón.'),
    // Vacío = turno sin paciente identificado: RN-AG-10 no aplica.
    patient_id: z.string(),
    tipo_practica: z.string(),
    fecha: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Elegí la fecha.'),
    hora: z.string().regex(/^\d{2}:\d{2}$/, 'Elegí la hora.'),
  })
  .refine((values) => localDateTimeToInstant(values.fecha, values.hora) !== null, {
    path: ['fecha'],
    message: 'La fecha y hora no son válidas.',
  })

type FormValues = z.infer<typeof appointmentSchema>

interface Options {
  patients: PatientOut[]
  professionals: ProfessionalOut[]
  chairs: ChairOut[]
}

const ES_TIPO_PRACTICA = (valor: string): valor is TipoPractica =>
  (TIPOS_PRACTICA as string[]).includes(valor)

/**
 * Formulario mínimo de agendamiento (task 7.1, criterio 4 del TPI).
 *
 * Es el vertical slice de la UI: consume la API real, sin mocks.
 *
 * * **Sin waterfalls** — pacientes, profesionales y sillones se piden con un solo
 *   `Promise.all`: el formulario no espera tres viajes encadenados.
 * * **Solo activos** — los recursos dados de baja no se ofrecen; si igual llegan
 *   al backend, el `409 recurso_inactivo` se muestra tal cual.
 * * **RN-AG-09** — la fecha y hora del input (hora de pared) se convierten a un
 *   instante UTC antes de enviar; el servidor nunca reinterpreta la zona.
 * * **Contrato** — `fin`, `duracion_min`, `estado` y `origen` no viajan: los
 *   deriva el servidor (RN-AG-03) y el schema los rechazaría con `422`.
 * * **Errores** — se conmutan por `code`: el `409` muestra recurso y rango en
 *   conflicto, el `404` "no existe o no tenés acceso" y el `422` datos inválidos.
 */
export default function NewAppointmentPage() {
  const { status, hasPermission } = useAuth()
  const canCreate = hasPermission('appointment.create')

  const form = useForm<FormValues>({
    resolver: zodResolver(appointmentSchema),
    defaultValues: {
      professional_id: '',
      chair_id: '',
      patient_id: '',
      tipo_practica: '',
      fecha: '',
      hora: '',
    },
  })

  const [options, setOptions] = useState<Options | null>(null)
  const [optionsError, setOptionsError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<ApiError | null>(null)
  const [created, setCreated] = useState<AppointmentOut | null>(null)

  useEffect(() => {
    if (!canCreate) return
    let cancelled = false
    setLoading(true)
    setOptionsError(null)

    Promise.all([listPatients({ limit: 100 }), listProfessionals(), listChairs()])
      .then(([pacientes, profesionales, sillones]) => {
        if (cancelled) return
        setOptions({
          patients: pacientes.patients,
          professionals: profesionales.professionals.filter((item) => item.activo),
          chairs: sillones.chairs.filter((item) => item.activo),
        })
      })
      .catch((error: unknown) => {
        if (!cancelled) setOptionsError(asApiError(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [canCreate])

  const onSubmit = form.handleSubmit(async (values) => {
    const inicio = localDateTimeToInstant(values.fecha, values.hora)
    if (inicio === null) return

    setSubmitError(null)
    setCreated(null)
    setSaving(true)
    try {
      const turno = await createAppointment({
        professional_id: values.professional_id,
        chair_id: values.chair_id,
        patient_id: values.patient_id === '' ? null : values.patient_id,
        inicio,
        ...(ES_TIPO_PRACTICA(values.tipo_practica) ? { tipo_practica: values.tipo_practica } : {}),
      })
      setCreated(turno)
      // El alta no limpia los selectores: recepción agenda varios turnos seguidos.
      form.setValue('fecha', '')
      form.setValue('hora', '')
    } catch (error) {
      setSubmitError(asApiError(error))
    } finally {
      setSaving(false)
    }
  })

  if (status === 'loading') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-4">
        <p role="status" className="text-sm text-muted-foreground">
          Cargando…
        </p>
      </main>
    )
  }

  if (!canCreate) {
    return <Forbidden />
  }

  if (optionsError !== null && optionsError.status === 403) {
    return <Forbidden code={optionsError.code} />
  }

  const conflicto = submitError === null ? null : conflictOf(submitError)
  const recurso = conflicto === null ? null : recursoLabel(conflicto.recurso)

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-4 bg-background p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-foreground">Nuevo turno</h1>
        <Link className="text-sm underline" to="/">
          Volver
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agendar un turno</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {loading ? (
            <p role="status" className="text-sm text-muted-foreground">
              Cargando profesionales y sillones…
            </p>
          ) : null}

          {!loading && optionsError !== null ? (
            <p className="text-sm text-destructive">{appointmentErrorMessage(optionsError)}</p>
          ) : null}

          {created !== null ? (
            <Alert role="status">
              <AlertDescription>
                Turno creado para el {formatRango(created.inicio, created.fin)} (
                {created.duracion_min} min). Estado: {created.estado}.
              </AlertDescription>
            </Alert>
          ) : null}

          {submitError !== null ? (
            <Alert variant="destructive">
              <AlertDescription>
                <p>{appointmentErrorMessage(submitError)}</p>
                {recurso !== null ? <p className="mt-1">Recurso en conflicto: {recurso}.</p> : null}
                {conflicto !== null && conflicto.inicio !== null && conflicto.fin !== null ? (
                  <p className="mt-1">
                    Turno existente: {formatRango(conflicto.inicio, conflicto.fin)}.
                  </p>
                ) : null}
                {submitError.code ? (
                  <p className="mt-1 text-xs">
                    Código: <code className="font-mono">{submitError.code}</code>
                  </p>
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}

          {!loading && options !== null ? (
            <form className="flex flex-col gap-3" noValidate onSubmit={onSubmit}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-profesional">Profesional</Label>
                  <select
                    id="turno-profesional"
                    className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                    aria-invalid={Boolean(form.formState.errors.professional_id)}
                    {...form.register('professional_id')}
                  >
                    <option value="">Elegí un profesional</option>
                    {options.professionals.map((profesional) => (
                      <option key={profesional.id} value={profesional.id}>
                        {profesional.apellido}, {profesional.nombre} ·{' '}
                        {profesional.duracion_default_min} min
                      </option>
                    ))}
                  </select>
                  {form.formState.errors.professional_id ? (
                    <p className="text-xs text-destructive">
                      {form.formState.errors.professional_id.message}
                    </p>
                  ) : null}
                </div>

                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-sillon">Sillón</Label>
                  <select
                    id="turno-sillon"
                    className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                    aria-invalid={Boolean(form.formState.errors.chair_id)}
                    {...form.register('chair_id')}
                  >
                    <option value="">Elegí un sillón</option>
                    {options.chairs.map((sillon) => (
                      <option key={sillon.id} value={sillon.id}>
                        {sillon.nombre}
                      </option>
                    ))}
                  </select>
                  {form.formState.errors.chair_id ? (
                    <p className="text-xs text-destructive">{form.formState.errors.chair_id.message}</p>
                  ) : null}
                </div>

                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-paciente">Paciente</Label>
                  <select
                    id="turno-paciente"
                    className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                    {...form.register('patient_id')}
                  >
                    <option value="">Sin paciente identificado</option>
                    {options.patients.map((paciente) => (
                      <option key={paciente.id} value={paciente.id}>
                        {paciente.apellido}, {paciente.nombre} ({paciente.numero_historia_clinica})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-tipo">Tipo de práctica</Label>
                  <select
                    id="turno-tipo"
                    className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
                    {...form.register('tipo_practica')}
                  >
                    <option value="">Sin especificar</option>
                    {TIPOS_PRACTICA.map((tipo) => (
                      <option key={tipo} value={tipo}>
                        {tipo}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-fecha">Fecha</Label>
                  <Input id="turno-fecha" type="date" {...form.register('fecha')} />
                  {form.formState.errors.fecha ? (
                    <p className="text-xs text-destructive">{form.formState.errors.fecha.message}</p>
                  ) : null}
                </div>

                <div className="flex flex-col gap-1">
                  <Label htmlFor="turno-hora">Hora</Label>
                  <Input id="turno-hora" type="time" {...form.register('hora')} />
                  {form.formState.errors.hora ? (
                    <p className="text-xs text-destructive">{form.formState.errors.hora.message}</p>
                  ) : null}
                </div>
              </div>

              <p className="text-xs text-muted-foreground">
                El fin y la duración los calcula el servidor a partir de la disponibilidad del
                profesional, del sillón y del tipo de práctica (RN-AG-03). La hora se envía a la
                API como instante UTC (RN-AG-09).
              </p>

              <div className="flex gap-2">
                <Button type="submit" disabled={saving || form.formState.isSubmitting}>
                  Guardar turno
                </Button>
              </div>
            </form>
          ) : null}

          {created !== null ? (
            <p className="text-sm text-muted-foreground">
              El turno quedó en estado pendiente. Creado: {formatInstant(created.inicio)}.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
