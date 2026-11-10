import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/context'

export default function Home() {
  const { session, signOut } = useAuth()

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-2xl font-semibold text-foreground">Gestión Odontológica</h1>
      {session ? (
        <p className="text-sm text-muted-foreground">
          {session.tenant.nombre_comercial} · {session.user.nombre} {session.user.apellido}
        </p>
      ) : null}
      <Button variant="outline" onClick={() => void signOut()}>
        Salir
      </Button>
    </main>
  )
}
