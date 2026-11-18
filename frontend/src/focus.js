// A button clicked with the mouse keeps focus, and Enter would then press it again.
// Dropping focus sends the next key press to the game instead.
// (event.detail is 0 when the "click" came from the keyboard, so keyboard users keep their place.)
export function blurAfterMouseClick(event) {
  if (event.detail > 0) {
    event.currentTarget.blur()
  }
}
