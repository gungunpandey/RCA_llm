import { useState } from 'react'
import RCAForm from './RCAForm'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Root Cause Analysis System</h1>
        <p>Submit equipment failure details for AI-powered analysis</p>
      </header>
      <main>
        <RCAForm />
      </main>
    </div>
  )
}

export default App
