// The "Players" panel: who is in the game, and a button that copies its invite link.
import { useState } from 'react'

// Who is in the game, and a button to copy its link for inviting others.
// A game with one player is a solo game; sharing its link is what makes it a shared one.
function Players({ game, currentUser }) {
  // '' before any click, then 'copied' or 'failed' for a couple of seconds
  const [copyState, setCopyState] = useState('')

  // the invite link is offered only while the game is going and has a free place
  const isFull = game.players.length >= game.max_players
  const canInvite = game.status === 'in_progress' && !isFull

  // Copies the page address to the clipboard, and shows for a few seconds whether it worked.
  async function copyLink(event) {
    // always give up focus, so the Enter that submits the next guess doesn't copy the link again
    event.currentTarget.blur()
    try {
      // the page address already names this game (?game=<id>), so the address is the invite
      await navigator.clipboard.writeText(window.location.href)
      setCopyState('copied')
    } catch {
      // some browsers block clipboard access; say so, and point to the address bar instead
      setCopyState('failed')
    }
    // back to the normal label after three seconds
    setTimeout(() => setCopyState(''), 3000)
  }

  return (
    <section className="players" aria-label="Players">
      <ul className="player-list">
        {game.players.map((player) => (
          <li key={player.id} className={player.id === currentUser.id ? 'player you' : 'player'}>
            {player.username}
            {player.id === currentUser.id && ' (you)'}
          </li>
        ))}
      </ul>

      <span className="player-count">
        {game.players.length} of {game.max_players} players
      </span>

      {canInvite && (
        <button className="link-button" onClick={copyLink}>
          {/* copyState has one value at a time, so exactly one of these three labels is drawn */}
          {copyState === 'copied' && 'Link copied!'}
          {copyState === 'failed' && "Couldn't copy. Share the address in your browser's address bar."}
          {copyState === '' && 'Copy invite link'}
        </button>
      )}
    </section>
  )
}

export default Players
