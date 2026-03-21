let timerInterval = null;
let elapsedSeconds = 0;

function startTimer(elementId, startFrom) {
    elapsedSeconds = startFrom || 0;
    const el = document.getElementById(elementId);
    if (timerInterval) clearInterval(timerInterval);

    // Display immediately
    updateTimerDisplay(el);

    timerInterval = setInterval(() => {
        if (!document.hidden) {
            elapsedSeconds++;
            updateTimerDisplay(el);
        }
    }, 1000);
}

function updateTimerDisplay(el) {
    const hours = Math.floor(elapsedSeconds / 3600);
    const mins = Math.floor((elapsedSeconds % 3600) / 60);
    const secs = elapsedSeconds % 60;
    if (hours > 0) {
        el.textContent = String(hours).padStart(2, '0') + ':' +
                         String(mins).padStart(2, '0') + ':' +
                         String(secs).padStart(2, '0');
    } else {
        el.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
    }
}

function getElapsedSeconds() {
    return elapsedSeconds;
}
