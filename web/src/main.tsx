import React from 'react'
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

class Boundary extends React.Component<{ children: React.ReactNode }, { err: any | null }> {
  state: { err: any } = { err: null }
  static getDerivedStateFromError(err: any) { return { err } }
  render() {
    if (this.state.err) {
      return (
        <div style={{ background: '#fff', color: '#c2402e', fontFamily: 'monospace', padding: 24, whiteSpace: 'pre-wrap' }}>
          <b>render error (report this):</b>{'\n'}
          {String(this.state.err?.message ?? this.state.err)}{'\n\n'}
          {String(this.state.err?.stack ?? '').slice(0, 900)}
        </div>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Boundary>
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
    </Boundary>
  </StrictMode>,
)
