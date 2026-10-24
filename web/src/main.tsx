import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Nav } from './components/chrome'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Research from './pages/Research'
import Docs from './pages/Docs'
import Live from './pages/Live'
import Predict from './pages/Predict'
import Voyage from './pages/Voyage'
import Analytics from './pages/Analytics'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/live" element={<Live />} />
        <Route path="/predict" element={<Predict />} />
        <Route path="/voyage/:id" element={<Voyage />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/research" element={<Research />} />
        <Route path="/docs" element={<Docs />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
