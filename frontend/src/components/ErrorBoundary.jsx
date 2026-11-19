// Catches a crash while drawing the page and shows a "something went wrong" message instead
// of a blank screen.
import { Component } from 'react'

// Catches an error thrown while React is drawing whatever is inside it. Without this, one
// unexpected error anywhere leaves the player looking at a blank page with no explanation.
// (React only offers this to class components, which is why this one is not a function.)
class ErrorBoundary extends Component {
  // Starts out healthy: nothing has failed yet.
  constructor(props) {
    super(props)
    this.state = { hasFailed: false }
  }

  // React calls this when something inside throws while drawing. The state it returns
  // switches render() below over to the fallback message.
  static getDerivedStateFromError() {
    return { hasFailed: true }
  }

  // React calls this after the failure, with the error itself. Used here only to log it.
  componentDidCatch(error) {
    // keep the detail where a developer can find it; the player gets a plain sentence
    console.error('The page failed while drawing:', error)
  }

  // Draws whatever is inside as normal, or the fallback message once something has failed.
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
