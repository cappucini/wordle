// The frontend's starting point: draws the App component into the page.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// This is where the app starts. index.html has an empty <div id="root">;
// createRoot hands that div to React, and render() tells React to draw <App /> inside it.
// StrictMode runs components twice in development to surface bugs; it does nothing in production.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
