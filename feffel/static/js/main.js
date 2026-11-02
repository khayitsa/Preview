'use strict';
// Entry point: runs once every other script has loaded.
if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {}); // installable app; never blocks startup
}
boot();
