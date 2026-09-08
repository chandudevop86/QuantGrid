import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import CustomerPageV2 from './CustomerPageV2.tsx'

const isOwner = window.location.pathname.replace(/\/+$/, '') === '/foodtruck/owner'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isOwner ? <App /> : <CustomerPageV2 />}
  </StrictMode>,
)
