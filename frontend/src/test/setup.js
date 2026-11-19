// Runs before every test file.
import '@testing-library/jest-dom/vitest' // adds checks such as toBeDisabled() and toHaveTextContent()
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  // remove whatever the test rendered, and put the address bar back to a plain page
  cleanup()
  window.history.replaceState({}, '', '/')
})
