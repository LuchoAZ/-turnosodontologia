import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation } from 'react-router-dom'
import { z } from 'zod'
import type { MfaEnrollStartResponse } from '@/api/auth'
import { ApiError } from '@/api/http'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/context'

const loginSchema = z.object({
  tenant_slug: z.string().trim().min(1, 'Ingresá la clínica.'),
  email: z.string().trim().min(3, 'Ingresá un email válido.'),
  password: z.string().min(1, 'Ingresá la contraseña.'),
})

const codeSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, 'El código tiene seis dígitos.'),
})

type LoginValues = z.infer<typeof loginSchema>
type CodeValues = z.infer<typeof codeSchema>

type Mode = 'idle' | 'mfaStepUp' | 'mfaEnrollment'

/** Mensaje de UI por `code` estable (design D9): nunca por status ni por texto. */
function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'invalid_credentials':
        return 'Email o contraseña incorrectos.'
      case 'locked': {
        const minutes = Math.max(1, Math.ceil((error.retryAfter ?? 0) / 60))
        return `La cuenta está bloqueada temporalmente. Reintentá en ${minutes} ${
          minutes === 1 ? 'minuto' : 'minutos'
        }.`
      }
      case 'mfa_step_up_expired':
        return 'La verificación expiró. Volvé a iniciar sesión.'
      case 'invalid_mfa_code':
        return 'El código de verificación es incorrecto.'
      case 'tenant_not_available':
        return 'La clínica no está disponible.'
      default:
        return error.message
    }
  }
  if (error instanceof TypeError) {
    return 'No pudimos conectar con el servidor. Reintentá en un momento.'
  }
  return 'Ocurrió un error inesperado. Reintentá en un momento.'
}

export default function Login() {
  const { status, signIn, startEnrollment, completeMfa, completeEnrollment } = useAuth()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [mode, setMode] = useState<Mode>('idle')
  const [error, setError] = useState<string | null>(null)
  const [enrollment, setEnrollment] = useState<MfaEnrollStartResponse | null>(null)

  const loginForm = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })
  const codeForm = useForm<CodeValues>({ resolver: zodResolver(codeSchema) })

  if (status === 'authenticated') {
    return <Navigate to={from} replace />
  }

  const fieldError =
    loginForm.formState.errors.tenant_slug?.message ??
    loginForm.formState.errors.email?.message ??
    loginForm.formState.errors.password?.message ??
    codeForm.formState.errors.code?.message

  const enterEnrollment = async () => {
    setMode('mfaEnrollment')
    try {
      setEnrollment(await startEnrollment())
    } catch (caught) {
      setMode('idle')
      setError(messageFor(caught))
    }
  }

  const onLogin = loginForm.handleSubmit(async (values) => {
    setError(null)
    try {
      const result = await signIn(values)
      if (result.kind === 'mfaStepUp') {
        setMode('mfaStepUp')
        return
      }
      if (result.kind === 'mfaEnrollment') {
        await enterEnrollment()
      }
    } catch (caught) {
      setError(messageFor(caught))
    }
  })

  const onCode = codeForm.handleSubmit(async ({ code }) => {
    setError(null)
    try {
      if (mode === 'mfaEnrollment') {
        await completeEnrollment(code)
      } else {
        await completeMfa(code)
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'mfa_step_up_expired') {
        setMode('idle')
        setEnrollment(null)
      }
      setError(messageFor(caught))
      codeForm.reset()
    }
  })

  const backToLogin = () => {
    setMode('idle')
    setEnrollment(null)
    setError(null)
    codeForm.reset()
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        {mode === 'idle' ? (
          <>
            <CardHeader>
              <CardTitle>
                <h1 className="text-xl font-semibold">Iniciar sesión</h1>
              </CardTitle>
              <CardDescription>Ingresá con la cuenta de tu clínica.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="flex flex-col gap-4" onSubmit={onLogin} noValidate>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="tenant_slug">Clínica</Label>
                  <Input
                    id="tenant_slug"
                    autoComplete="organization"
                    aria-invalid={Boolean(loginForm.formState.errors.tenant_slug)}
                    {...loginForm.register('tenant_slug')}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    aria-invalid={Boolean(loginForm.formState.errors.email)}
                    {...loginForm.register('email')}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Contraseña</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    aria-invalid={Boolean(loginForm.formState.errors.password)}
                    {...loginForm.register('password')}
                  />
                </div>
                <Button type="submit" disabled={loginForm.formState.isSubmitting}>
                  Ingresar
                </Button>
              </form>
            </CardContent>
          </>
        ) : null}

        {mode !== 'idle' ? (
          <>
            <CardHeader>
              <CardTitle>
                <h1 className="text-xl font-semibold">
                  {mode === 'mfaEnrollment' ? 'Configurá el segundo factor' : 'Verificación en dos pasos'}
                </h1>
              </CardTitle>
              <CardDescription>
                {mode === 'mfaEnrollment'
                  ? 'Agregá este secreto en tu aplicación autenticadora y confirmá el código.'
                  : 'Ingresá el código de tu aplicación autenticadora.'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {mode === 'mfaEnrollment' && enrollment ? (
                <p className="mb-4 rounded-md bg-muted p-2 text-center font-mono text-sm break-all">
                  {enrollment.secret}
                </p>
              ) : null}
              <form className="flex flex-col gap-4" onSubmit={onCode} noValidate>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="code">Código de verificación</Label>
                  <Input
                    id="code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    aria-invalid={Boolean(codeForm.formState.errors.code)}
                    {...codeForm.register('code')}
                  />
                </div>
                <Button type="submit" disabled={codeForm.formState.isSubmitting}>
                  {mode === 'mfaEnrollment' ? 'Confirmar' : 'Verificar'}
                </Button>
                <Button type="button" variant="ghost" onClick={backToLogin}>
                  Volver
                </Button>
              </form>
            </CardContent>
          </>
        ) : null}

        {error ?? fieldError ? (
          <CardContent>
            <Alert variant="destructive">
              <AlertDescription>{error ?? fieldError}</AlertDescription>
            </Alert>
          </CardContent>
        ) : null}
      </Card>
    </main>
  )
}
