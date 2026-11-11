/**
 * Cliente de gestión de equipo (C-04, design D6).
 *
 * Los `code` de error son los del catálogo estable del backend
 * (`app/domain/rbac/errors.py`): la UI conmuta por `code`, nunca por status ni
 * por texto. El `tenant_id` no viaja nunca: sale de la sesión en el servidor.
 */

import type { Role } from './auth'
import type { AssignableRole } from '@/features/team/roles'
import { apiFetch } from './http'

export interface MemberOut {
  id: string
  user_id: string
  email: string | null
  nombre: string
  apellido: string
  rol: Role
  activo: boolean
  professional_id: string | null
}

export interface MemberListOut {
  members: MemberOut[]
}

/** Permisos que esta pantalla consulta (subconjunto de la matriz de 57). */
export type TeamPermission =
  | 'team.read'
  | 'team.create'
  | 'team.update'
  | 'team.delete'
  | 'ownership.transfer'

/** Roles que se pueden asignar desde la UI (`owner` solo por transferencia). */

export function listMembers(): Promise<MemberListOut> {
  return apiFetch<MemberListOut>('/team/members')
}

export function changeRole(membershipId: string, rol: AssignableRole): Promise<MemberOut> {
  return apiFetch<MemberOut>(`/team/members/${membershipId}`, {
    method: 'PATCH',
    body: JSON.stringify({ rol }),
  })
}

export function deactivateMember(membershipId: string): Promise<void> {
  return apiFetch<void>(`/team/members/${membershipId}`, { method: 'DELETE' })
}

export function transferOwnership(
  targetMembershipId: string,
  previousOwnerRole: AssignableRole,
): Promise<MemberListOut> {
  return apiFetch<MemberListOut>('/team/ownership-transfer', {
    method: 'POST',
    body: JSON.stringify({
      target_membership_id: targetMembershipId,
      previous_owner_role: previousOwnerRole,
    }),
  })
}
