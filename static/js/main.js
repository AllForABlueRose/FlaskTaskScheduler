window.onload = async () => {
    const today = parseISO(TODAY_ISO);
    dayAnchor = today;
    weekAnchor = mondayOf(today);
    const rs = document.body.dataset.rangeStart;
    const re = document.body.dataset.rangeEnd;
    if (rs) validRangeStart = parseISO(rs);
    if (re) validRangeEnd = parseISO(re);

    const hour = new Date().getHours();
    applyView('week');
    applyMode((hour >= 8 && hour < 20) ? 'day' : 'night');
    await loadTasks();
    await loadSchedule();
    setInterval(updateNowLine, 30000);
    setInterval(async () => {
        await loadTasks();
        await loadSchedule();
    }, 5000);
};
