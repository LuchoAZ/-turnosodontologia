import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { ApiError } from '@/api/http'
import {
  candidatesOf,
  createPatient,
  listPatients,
  updatePatient,
} from '@/api/patients'
import type { PatientCandidate, PatientIn, PatientOut } from '@/api/patients'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Forbidden from '@/features/auth/Forbidden'
import { useAuth } from '@/features/auth/context'
import DuplicateDialog from './DuplicateDialog'
import PatientFormDialog from './PatientFormDialog'
import { asApiError, patientErrorMessage } from './errors'

interface DuplicateState {
  payload: PatientIn
  candidates: PatientCandidate[]
}

/**
 * Pantalla de pacientes (tasks 5.2–5.5, S11.1–S11.5).
 *
 * La autorización real es del backend (`require_permission`): la ruta se protege
 * con `patient.read` y acá solo se ocultan las acciones sin permiso. Los errores
 * se conmutan por `code`: `patient_dni_duplicado` es un conflicto no confirmable,
 * `patient_posible_duplicado` abre el diálogo de candidatos y `forbidden` se
 * informa como falta de permisos.
 */
export default function PatientsPage() {
  const { status, hasPermission } = useAuth()
  const canRead = hasPermission('patient.read')
  const canCreate = hasPermission('patient.create')
  const canUpdate = hasPermission('patient.update')

  const [patients, setPatients] = useState<PatientOut[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [termino, setTermino] = useState('')
  const [incluirInactivos, setIncluirInactivos] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<PatientOut | null>(null)
  const [formError, setFormError] = useState<ApiError | null>(null)
  const [saving, setSaving] = useState(false)
  const [duplicate, setDuplicate] = useState<DuplicateState | null>(null)

  const load = useCallback(async (q: string, inactivos: boolean) => {
    setLoading(true)
    setListError(null)
    try {
      const data = await listPatients({
        q,
        ...(inactivos ? { incluir_inactivos: true } : {}),
      })
      setPatients(data.patients)
      setTotal(data.total)
    } catch (error) {
      setListError(asApiError(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!canRead) return
    void load('', false)
  }, [canRead, load])

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void load(termino.trim(), incluirInactivos)
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditing(null)
    setFormError(null)
    setDuplicate(null)
  }

  const openCreate = () => {
    setEditing(null)
    setFormError(null)
    setFormOpen(true)
  }

  const openEdit = (patient: PatientOut) => {
    setEditing(patient)
    setFormError(null)
    setFormOpen(true)
  }

  const applyCreated = (created: PatientOut) => {
    setPatients((current) => [created, ...current])
    setTotal((current) => current + 1)
    setNotice(`Paciente creado con HCE ${created.numero_historia_clinica}.`)
  }

  const onSubmit = async (values: PatientIn) => {
    setSaving(true)
    setFormError(null)
    setNotice(null)
    try {
      if (editing !== null) {
        const updated = await updatePatient(editing.id, values)
        setPatients((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setNotice(`Ficha actualizada: ${updated.apellido}, ${updated.nombre}.`)
        closeForm()
      } else {
        const created = await createPatient(values)
        applyCreated(created)
        closeForm()
      }
    } catch (error) {
      const api = asApiError(error)
      // Solo el dedupe blando se puede confirmar; el `409` por DNI es terminal.
      if (api.code === 'patient_posible_duplicado') {
        setDuplicate({ payload: values, candidates: candidatesOf(api) })
        return
      }
      setFormError(api)
    } finally {
      setSaving(false)
    }
  }

  const onConfirmDuplicate = async () => {
    if (duplicate === null) return
    setSaving(true)
    try {
      const created = await createPatient({ ...duplicate.payload, confirmar_duplicado: true })
      setDuplicate(null)
      applyCreated(created)
      closeForm()
    } catch (error) {
      setDuplicate(null)
      setFormError(asApiError(error))
    } finally {
      setSaving(false)
    }
  }

  if (status === 'loading') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-4">
        <p role="status" className="text-sm text-muted-foreground">
          Cargando…
        </p>
      </main>
    )
  }

  if (!canRead) {
    return <Forbidden />
  }

  if (listError !== null && listError.status === 403) {
    return <Forbidden code={listError.code} />
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-4 bg-background p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-foreground">Pacientes</h1>
        <Link className="text-sm underline" to="/">
          Volver
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Fichas de la clínica</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {notice ? (
            <Alert>
              <AlertDescription>{notice}</AlertDescription>
            </Alert>
          ) : null}

          <form className="flex flex-wrap items-end gap-3" onSubmit={onSearch}>
            <div className="flex flex-col gap-1">
              <Label htmlFor="patient-buscar">Buscar paciente</Label>
              <Input
                id="patient-buscar"
                placeholder="Apellido, nombre, DNI o teléfono"
                value={termino}
                onChange={(event) => setTermino(event.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={incluirInactivos}
                onChange={(event) => setIncluirInactivos(event.target.checked)}
              />
              Incluir dados de baja
            </label>
            <Button type="submit">Buscar</Button>
            {canCreate ? (
              <Button type="button" variant="outline" onClick={openCreate}>
                Nuevo paciente
              </Button>
            ) : null}
          </form>

          {loading ? (
            <p role="status" className="text-sm text-muted-foreground">
              Cargando…
            </p>
          ) : null}
          {!loading && listError !== null ? (
            <p className="text-sm text-destructive">{patientErrorMessage(listError)}</p>
          ) : null}

          <p className="text-sm text-muted-foreground">
            {total === 1 ? '1 paciente' : `${total} pacientes`}
          </p>

          {patients.length === 0 && !loading && listError === null ? (
            <p className="text-sm text-muted-foreground">No hay pacientes para mostrar.</p>
          ) : null}

          {patients.length > 0 ? (
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-2 pr-2">
                    HCE
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Paciente
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    DNI
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Teléfono
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Estado
                  </th>
                  {canUpdate ? (
                    <th scope="col" className="py-2">
                      Acciones
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {patients.map((patient) => (
                  <tr key={patient.id} className="border-b align-middle">
                    <td className="py-2 pr-2 font-mono">{patient.numero_historia_clinica}</td>
                    <td className="py-2 pr-2">
                      {patient.apellido}, {patient.nombre}
                    </td>
                    <td className="py-2 pr-2">{patient.dni ?? '—'}</td>
                    <td className="py-2 pr-2">{patient.telefono}</td>
                    <td className="py-2 pr-2">{patient.activo ? 'Activo' : 'Inactivo'}</td>
                    {canUpdate ? (
                      <td className="py-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => openEdit(patient)}
                        >
                          Editar
                        </Button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}

          {formOpen ? (
            <PatientFormDialog
              key={editing?.id ?? 'nuevo'}
              patient={editing}
              error={formError}
              saving={saving}
              onSubmit={(values) => void onSubmit(values)}
              onClose={closeForm}
            />
          ) : null}

          {duplicate !== null ? (
            <DuplicateDialog
              candidates={duplicate.candidates}
              onConfirm={() => void onConfirmDuplicate()}
              onCancel={() => setDuplicate(null)}
            />
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
