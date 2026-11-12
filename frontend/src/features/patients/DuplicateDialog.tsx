import { useState } from 'react'
import type { PatientCandidate } from '@/api/patients'
import { Button } from '@/components/ui/button'

interface DuplicateDialogProps {
  candidates: PatientCandidate[]
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Confirmación del `409 patient_posible_duplicado` (task 5.4, S11.4).
 *
 * Solo se abre para el dedupe **blando**: el backend acepta `confirmar_duplicado`
 * y crea la segunda ficha. El `409 patient_dni_duplicado` no pasa por acá porque
 * esa regla no se puede vencer.
 */
export default function DuplicateDialog({
  candidates,
  onConfirm,
  onCancel,
}: DuplicateDialogProps) {
  const [confirmando, setConfirmando] = useState(false)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Posible duplicado"
      className="flex flex-col gap-3 rounded-md border border-dashed border-input p-4"
    >
      <h2 className="text-lg font-semibold text-foreground">Posible duplicado</h2>
      <p className="text-sm text-muted-foreground">
        Ya existen pacientes con datos parecidos. Si es la misma persona, usá la ficha existente; si
        es otra persona, confirmá el alta.
      </p>
      <ul className="flex flex-col gap-1 text-sm">
        {candidates.map((candidate) => (
          <li key={candidate.id} className="rounded border border-input p-2">
            <span className="font-medium">
              {candidate.apellido}, {candidate.nombre}
            </span>
            {' · '}
            HCE <code className="font-mono">{candidate.numero_historia_clinica}</code>
            {' · '}
            DNI {candidate.dni ?? 'sin DNI'}
            {' · '}
            {candidate.telefono}
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button
          type="button"
          disabled={confirmando}
          onClick={() => {
            setConfirmando(true)
            onConfirm()
          }}
        >
          Confirmar alta
        </Button>
      </div>
    </div>
  )
}
