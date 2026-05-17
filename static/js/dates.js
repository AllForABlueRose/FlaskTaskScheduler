function parseISO(s){ return new Date(s + 'T00:00:00'); }

function isoDate(d){
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
}

function addDays(d, n){
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    r.setHours(0,0,0,0);
    return r;
}

function mondayOf(d){
    const r = new Date(d);
    r.setHours(0,0,0,0);
    const wd = r.getDay();
    const off = wd === 0 ? -6 : 1 - wd;
    r.setDate(r.getDate() + off);
    return r;
}

function isSameDate(a, b){
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function displayedMonday(){
    return currentView === 'day' ? mondayOf(dayAnchor) : weekAnchor;
}

function displayedDates(){
    const start = displayedMonday();
    return Array.from({length: 7}, (_, i) => addDays(start, i));
}

function viewVisibleDates(){
    const dates = displayedDates();
    if (currentView === 'day') {
        const target = isoDate(dayAnchor);
        return dates.filter(d => isoDate(d) === target);
    }
    if (currentView === 'weekday') {
        return dates.filter(d => { const w = d.getDay(); return w >= 1 && w <= 5; });
    }
    return dates;
}

function getVisibleDays(){
    return viewVisibleDates().map(isoDate);
}

function isTodayVisible(){
    return getVisibleDays().includes(TODAY_ISO);
}
