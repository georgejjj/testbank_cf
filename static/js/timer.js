let timerInterval = null;
let elapsedSeconds = 0;

function startTimer(elementId) {
    elapsedSeconds = 0;
    const el = document.getElementById(elementId);
    if (timerInterval) clearInterval(timerInterval);

    timerInterval = setInterval(() => {
        if (!document.hidden) {
            elapsedSeconds++;
            const mins = Math.floor(elapsedSeconds / 60);
            const secs = elapsedSeconds % 60;
            el.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
        }
    }, 1000);
}

function getElapsedSeconds() {
    return elapsedSeconds;
}

// Reset timer when HTMX swaps question content
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'question-panel') {
        startTimer('timer');
    }
});
