import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface ForbiddenProps {
  /** `code` estable de la API (`forbidden`, `membership_not_found`…), si vino de una request. */
  code?: string | null
  /** Texto alternativo; por defecto el de la pantalla de Equipo (task 11.2). */
  message?: string
}

/**
 * Acceso denegado (design D9).
 *
 * Se muestra cuando la UI sabe que la sesión no tiene el permiso **o** cuando la
 * API responde `403`/`404`. El `code` se muestra tal cual: es el contrato
 * estable para diagnosticar y para el guion de la demo, nunca el `detail` de
 * Pydantic ni el mensaje crudo de la base.
 */
export default function Forbidden({
  code = null,
  message = 'No tenés permiso para ver esta sección.',
}: ForbiddenProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Alert variant="destructive" className="w-full max-w-md">
        <AlertTitle>Acceso denegado</AlertTitle>
        <AlertDescription>
          <p>{message}</p>
          {code ? (
            <p className="mt-2 text-xs">
              Código: <code className="font-mono">{code}</code>
            </p>
          ) : null}
        </AlertDescription>
      </Alert>
    </main>
  )
}
