import { Component } from 'react'

// Catches an error thrown while React is drawing whatever is inside it. Without this, one
// unexpected error anywhere leaves the player looking at a blank page with no explanation.
// (React only offers this to class components, which is why this one is not a function.)
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasFailed: false }
  }

  static getDerivedStateFromError() {
    return { hasFailed: true }
  }

  componentDidCatch(error) {
    // keep the detail where a developer can find it; the player gets a plain sentence
    console.error('The page failed while drawing:', error)
  }

  render() {
    if (!this.state.hasFailed) {
      return this.props.children
    }
    return (
      <div className="auth-form" role="alert">
        <p>Something went wrong. Your games are saved.</p>
        <button className="new-game" onClick={() => window.location.reload()}>
          Reload the page
        </button>
      </div>
    )
  }
}

export default ErrorBoundary
