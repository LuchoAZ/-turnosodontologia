import { Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthProvider'
import RequireAuth from './features/auth/RequireAuth'
import RequirePermission from './features/auth/RequirePermission'
import ClinicPage from './features/clinic/ClinicPage'
import NewAppointmentPage from './features/agenda/NewAppointmentPage'
import PatientsPage from './features/patients/PatientsPage'
import TeamPage from './features/team/TeamPage'
import Home from './routes/Home'
import Login from './routes/Login'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Home />} />
          <Route
            path="/equipo"
            element={
              <RequirePermission permission="team.read">
                <TeamPage />
              </RequirePermission>
            }
          />
          <Route
            path="/clinica"
            element={
              <RequirePermission permission="chair.read">
                <ClinicPage />
              </RequirePermission>
            }
          />
          <Route
            path="/pacientes"
            element={
              <RequirePermission permission="patient.read">
                <PatientsPage />
              </RequirePermission>
            }
          />
          <Route
            path="/turnos/nuevo"
            element={
              <RequirePermission permission="appointment.create">
                <NewAppointmentPage />
              </RequirePermission>
            }
          />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
