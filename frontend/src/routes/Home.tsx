import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/context'

export default function Home() {
  const { session, signOut, hasPermission } = useAuth()

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-2xl font-semibold text-foreground">Gestión Odontológica</h1>
      {session ? (
        <p className="text-sm text-muted-foreground">
          {session.tenant.nombre_comercial} · {session.user.nombre} {session.user.apellido}
        </p>
      ) : null}
      {hasPermission('team.read') ? (
        <Link className="text-sm underline" to="/equipo">
          Equipo
        </Link>
      ) : null}
      {hasPermission('chair.read') ? (
        <Link className="text-sm underline" to="/clinica">
          Clínica
        </Link>
      ) : null}
      {hasPermission('patient.read') ? (
        <Link className="text-sm underline" to="/pacientes">
          Pacientes
        </Link>
      ) : null}
      {hasPermission('appointment.create') ? (
        <Link className="text-sm underline" to="/turnos/nuevo">
          Agendar turno
        </Link>
      ) : null}
      <Button variant="outline" onClick={() => void signOut()}>
        Salir
      </Button>
    </main>
  )
}
