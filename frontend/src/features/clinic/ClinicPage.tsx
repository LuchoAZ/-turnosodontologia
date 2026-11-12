import { Link } from 'react-router-dom'
import { useAuth } from '@/features/auth/context'
import AvailabilitySection from './AvailabilitySection'
import ChairsSection from './ChairsSection'
import ProfessionalsSection from './ProfessionalsSection'

/**
 * Pantalla de configuración de la clínica (tasks 7.4–7.5).
 *
 * La ruta se protege con `chair.read`; cada sección se muestra según su propio
 * permiso de lectura. La autorización real la hace el backend: forzar el
 * endpoint sin permiso devuelve `403 forbidden` igual.
 */
export default function ClinicPage() {
  const { hasPermission } = useAuth()
  const canReadProfessionals = hasPermission('professional.read')

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-4 bg-background p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-foreground">Clínica</h1>
        <Link className="text-sm underline" to="/">
          Volver
        </Link>
      </div>

      <ChairsSection />

      {canReadProfessionals ? (
        <>
          <ProfessionalsSection />
          <AvailabilitySection />
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Necesitás el permiso de lectura de profesionales para ver profesionales y disponibilidad.
        </p>
      )}
    </main>
  )
}
