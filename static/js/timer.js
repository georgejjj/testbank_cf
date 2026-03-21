let timerInterval = null;
let elapsedSeconds = 0;
let timerKey = '';  // localStorage key per assignment

function startTimer(elementId, startFrom, assignmentKey) {
    timerKey = 'timer_' + (assignmentKey || 'default');

    // Use localStorage value if it's higher than server value (more recent)
    var stored = parseInt(localStorage.getItem(timerKey) || '0');
    elapsedSeconds = Math.max(startFrom || 0, stored);

    const el = document.getElementById(elementId);
    if (timerInterval) clearInterval(timerInterval);

    updateTimerDisplay(el);

    timerInterval = setInterval(() => {
        if (!document.hidden) {
            elapsedSeconds++;
            updateTimerDisplay(el);
            localStorage.setItem(timerKey, elapsedSeconds);
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
    // Also save to localStorage when reading
    if (timerKey) localStorage.setItem(timerKey, elapsedSeconds);
    return elapsedSeconds;
}

function clearTimerStorage(assignmentKey) {
    localStorage.removeItem('timer_' + (assignmentKey || 'default'));
}
