import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './c-shell.css'
import './app.css'
import './review.css'
import './summary.css'
import './lp.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
