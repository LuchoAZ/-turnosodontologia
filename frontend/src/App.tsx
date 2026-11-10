import { Route, Routes } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthProvider'
import RequireAuth from './features/auth/RequireAuth'
import Home from './routes/Home'
import Login from './routes/Login'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Home />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
