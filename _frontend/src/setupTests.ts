import '@testing-library/jest-dom'

// jsdom does not implement layout/scrolling; stub scrollIntoView so the StageNav
// active-step effect is a safe no-op (individual tests may spy on this).
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
