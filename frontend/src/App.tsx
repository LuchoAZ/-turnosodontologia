import { Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthProvider'
import RequireAuth from './features/auth/RequireAuth'
import RequirePermission from './features/auth/RequirePermission'
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
        </Route>
      </Routes>
    </AuthProvider>
  )
}
