import { useCallback, useEffect, useRef, useState } from 'react'

// The "How to play" panel: whether it is open, and every way of opening and closing it.
//
//   open or close:  the button in the bar, or the ? key
//   close:          Escape, or a click anywhere outside the panel
//
// The panel does not take over the page. The board stays visible behind it, and closing it
// puts the player straight back in the game.
export function useRulesPanel() {
  const [isOpen, setIsOpen] = useState(false)
  // the button and the panel, so a click on either is not taken for a click "outside"
  const buttonRef = useRef(null)
  const panelRef = useRef(null)

  // Closing also takes focus off the button. A player who opened the rules by pressing Enter
  // on it would otherwise still be on it, and their next Enter would open the rules again
  // instead of sending their guess.
  const close = useCallback(() => {
    setIsOpen(false)
    if (document.activeElement === buttonRef.current) {
      buttonRef.current.blur()
    }
  }, [])

  const toggle = useCallback(() => {
    if (isOpen) {
      close()
    } else {
      setIsOpen(true)
    }
  }, [isOpen, close])

  // The ? key works whether the panel is open or closed.
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return // leave browser shortcuts alone
      }
      if (event.key === '?') {
        event.preventDefault()
        toggle()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggle])

  // Escape and outside clicks only need watching while the panel is open.
  useEffect(() => {
    if (!isOpen) {
      return
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        close()
      }
    }
    function handlePointerDown(event) {
      const isInside =
        (panelRef.current !== null && panelRef.current.contains(event.target)) ||
        (buttonRef.current !== null && buttonRef.current.contains(event.target))
      if (!isInside) {
        close()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('pointerdown', handlePointerDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [isOpen, close])

  return { isOpen, toggle, buttonRef, panelRef }
}
