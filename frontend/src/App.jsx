import { Navigate, Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar'
import DashboardPage from './pages/DashboardPage'
import GraphPage from './pages/GraphPage'
import HomePage from './pages/HomePage'
import StocksPage from './pages/StocksPage'
import './App.css'

function App() {
  return (
    <div className="app-shell">
      <NavBar />
      <main className="app-content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/stocks" element={<StocksPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
