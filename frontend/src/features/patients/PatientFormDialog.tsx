import { useState } from 'react'
import type { FormEvent } from 'react'
import type { ApiError } from '@/api/http'
import type { PatientIn, PatientOut, Sexo } from '@/api/patients'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { patientErrorMessage } from './errors'

const SEXO_OPTIONS: { value: '' | Sexo; label: string }[] = [
  { value: '', label: 'Sin declarar' },
  { value: 'femenino', label: 'Femenino' },
  { value: 'masculino', label: 'Masculino' },
  { value: 'otro', label: 'Otro' },
  { value: 'no_declara', label: 'Prefiere no declarar' },
]

interface Draft {
  nombre: string
  apellido: string
  telefono: string
  dni: string
  fecha_nacimiento: string
  sexo: '' | Sexo
  email: string
  calle: string
  numero: string
  localidad: string
}

function draftFrom(patient: PatientOut | null): Draft {
  return {
    nombre: patient?.nombre ?? '',
    apellido: patient?.apellido ?? '',
    telefono: patient?.telefono ?? '',
    dni: patient?.dni ?? '',
    fecha_nacimiento: patient?.fecha_nacimiento ?? '',
    sexo: (patient?.sexo as Sexo | null) ?? '',
    email: patient?.email ?? '',
    calle: patient?.domicilio?.calle ?? '',
    numero: patient?.domicilio?.numero ?? '',
    localidad: patient?.domicilio?.localidad ?? '',
  }
}

function validar(draft: Draft): string | null {
  if (draft.nombre.trim() === '' || draft.apellido.trim() === '' || draft.telefono.trim() === '') {
    return 'Completá nombre, apellido y teléfono.'
  }
  if (draft.dni.trim() !== '' && !/^\d{7,11}$/.test(draft.dni.trim())) {
    return 'El DNI debe tener entre 7 y 11 dígitos, sin puntos ni guiones.'
  }
  if (draft.email.trim() !== '' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(draft.email.trim())) {
    return 'El email no tiene un formato válido.'
  }
  return null
}

function toPayload(draft: Draft): PatientIn {
  const payload: PatientIn = {
    nombre: draft.nombre.trim(),
    apellido: draft.apellido.trim(),
    telefono: draft.telefono.trim(),
  }
  if (draft.dni.trim() !== '') payload.dni = draft.dni.trim()
  if (draft.fecha_nacimiento !== '') payload.fecha_nacimiento = draft.fecha_nacimiento
  if (draft.sexo !== '') payload.sexo = draft.sexo
  if (draft.email.trim() !== '') payload.email = draft.email.trim()
  if (draft.calle.trim() !== '' || draft.numero.trim() !== '' || draft.localidad.trim() !== '') {
    payload.domicilio = {
      calle: draft.calle.trim() === '' ? null : draft.calle.trim(),
      numero: draft.numero.trim() === '' ? null : draft.numero.trim(),
      localidad: draft.localidad.trim() === '' ? null : draft.localidad.trim(),
    }
  }
  return payload
}

interface PatientFormDialogProps {
  /** `null` = alta; una ficha = edición. */
  patient: PatientOut | null
  error: ApiError | null
  saving: boolean
  onSubmit: (values: PatientIn) => void
  onClose: () => void
}

/**
 * Formulario de alta y edición de la ficha (tasks 5.3, S11.2–S11.4).
 *
 * El diálogo no llama a la API: el padre decide si es `POST` o `PATCH` y qué
 * hacer con el `409`. Como el componente sigue montado mientras hay error, los
 * valores cargados se conservan (S11.3) y el usuario puede corregir el DNI.
 */
export default function PatientFormDialog({
  patient,
  error,
  saving,
  onSubmit,
  onClose,
}: PatientFormDialogProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(patient))
  const [localError, setLocalError] = useState<string | null>(null)

  const esEdicion = patient !== null

  const set = <K extends keyof Draft>(campo: K, valor: Draft[K]) => {
    setDraft((current) => ({ ...current, [campo]: valor }))
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const invalido = validar(draft)
    if (invalido !== null) {
      setLocalError(invalido)
      return
    }
    setLocalError(null)
    onSubmit(toPayload(draft))
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={esEdicion ? 'Editar paciente' : 'Nuevo paciente'}
      className="flex flex-col gap-4 rounded-md border border-input p-4"
    >
      <h2 className="text-lg font-semibold text-foreground">
        {esEdicion ? 'Editar paciente' : 'Nuevo paciente'}
      </h2>

      {localError ? (
        <Alert variant="destructive">
          <AlertDescription>{localError}</AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>
            <p>{patientErrorMessage(error)}</p>
            {error.code ? (
              <p className="mt-1 text-xs">
                Código: <code className="font-mono">{error.code}</code>
              </p>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <form className="flex flex-col gap-3" noValidate onSubmit={handleSubmit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-nombre">Nombre</Label>
            <Input
              id="patient-nombre"
              value={draft.nombre}
              onChange={(event) => set('nombre', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-apellido">Apellido</Label>
            <Input
              id="patient-apellido"
              value={draft.apellido}
              onChange={(event) => set('apellido', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-telefono">Teléfono</Label>
            <Input
              id="patient-telefono"
              value={draft.telefono}
              onChange={(event) => set('telefono', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-dni">DNI</Label>
            <Input
              id="patient-dni"
              inputMode="numeric"
              value={draft.dni}
              onChange={(event) => set('dni', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-fecha-nacimiento">Fecha de nacimiento</Label>
            <Input
              id="patient-fecha-nacimiento"
              type="date"
              value={draft.fecha_nacimiento}
              onChange={(event) => set('fecha_nacimiento', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-sexo">Sexo</Label>
            <select
              id="patient-sexo"
              className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
              value={draft.sexo}
              onChange={(event) => set('sexo', event.target.value as '' | Sexo)}
            >
              {SEXO_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1 sm:col-span-2">
            <Label htmlFor="patient-email">Email</Label>
            <Input
              id="patient-email"
              type="email"
              value={draft.email}
              onChange={(event) => set('email', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-calle">Calle</Label>
            <Input
              id="patient-calle"
              value={draft.calle}
              onChange={(event) => set('calle', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-numero">Número</Label>
            <Input
              id="patient-numero"
              value={draft.numero}
              onChange={(event) => set('numero', event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="patient-localidad">Localidad</Label>
            <Input
              id="patient-localidad"
              value={draft.localidad}
              onChange={(event) => set('localidad', event.target.value)}
            />
          </div>
        </div>

        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            Guardar paciente
          </Button>
        </div>
      </form>
    </div>
  )
}
