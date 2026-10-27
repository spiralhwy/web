{# Calendar navigation for calendar.njk. Set `calendarDates` (sorted YYYY-MM-DD strings) before including. #}
        (function() {
            const dates = {{ calendarDates | dump | safe }};
            // Only link dates that still have upcoming showings on the page.
            const dateSet = new Set(dates.filter(function(d) {
                return document.getElementById('date-' + d);
            }));

            const firstDate = dates[0];
            const lastDate = dates[dates.length - 1];
            const firstMonth = new Date(firstDate.replace(/-/g, '/'));
            firstMonth.setDate(1);
            const lastMonth = new Date(lastDate.replace(/-/g, '/'));
            lastMonth.setDate(1);

            // build list of months to render (first to last, inclusive)
            const months = [];
            const cursor = new Date(firstMonth);
            while (cursor <= lastMonth) {
                months.push(new Date(cursor));
                cursor.setMonth(cursor.getMonth() + 1);
            }

            let currentIdx = 0;
            // start on the month containing today if possible
            const today = new Date();
            const todayStr = today.getFullYear() + '-' +
                String(today.getMonth() + 1).padStart(2, '0') + '-' +
                String(today.getDate()).padStart(2, '0');
            for (let i = 0; i < months.length; i++) {
                if (today.getFullYear() === months[i].getFullYear() &&
                    today.getMonth() === months[i].getMonth()) {
                    currentIdx = i;
                    break;
                }
            }

            const monthNames = ['January','February','March','April','May','June',
                                'July','August','September','October','November','December'];
            const label = document.getElementById('cal-month-label');
            const daysEl = document.getElementById('cal-days');
            const prevBtn = document.getElementById('cal-prev');
            const nextBtn = document.getElementById('cal-next');

            function pad(n) { return String(n).padStart(2, '0'); }

            function render() {
                const m = months[currentIdx];
                const year = m.getFullYear();
                const month = m.getMonth();
                label.textContent = monthNames[month] + ' ' + year;

                // prev/next visibility
                prevBtn.style.visibility = currentIdx === 0 ? 'hidden' : 'visible';
                nextBtn.style.visibility = currentIdx === months.length - 1 ? 'hidden' : 'visible';

                // build days
                const firstDow = new Date(year, month, 1).getDay();
                const daysInMonth = new Date(year, month + 1, 0).getDate();

                let html = '';
                // blank cells for offset
                for (let i = 0; i < firstDow; i++) {
                    html += '<span class="cal-day"></span>';
                }
                for (let d = 1; d <= daysInMonth; d++) {
                    const ds = year + '-' + pad(month + 1) + '-' + pad(d);
                    const hasListings = dateSet.has(ds);
                    const isToday = ds === todayStr;
                    let cls = 'cal-day';
                    if (hasListings) cls += ' cal-day-active';
                    else cls += ' cal-day-inactive';
                    if (isToday) cls += ' cal-day-today';
                    if (hasListings) {
                        html += '<a href="#date-' + ds + '" class="' + cls + '">' + d + '</a>';
                    } else {
                        html += '<span class="' + cls + '">' + d + '</span>';
                    }
                }
                daysEl.innerHTML = html;

                // smooth scroll on click
                daysEl.querySelectorAll('a.cal-day-active').forEach(function(el) {
                    el.addEventListener('click', function(e) {
                        e.preventDefault();
                        var target = document.querySelector(el.getAttribute('href'));
                        if (target) {
                            scrollTarget = target;
                            function onScrollEnd() {
                                window.removeEventListener('scrollend', onScrollEnd);
                                if (scrollTarget) {
                                    scrollTarget.classList.remove('flash');
                                    void scrollTarget.offsetWidth;
                                    scrollTarget.classList.add('flash');
                                    scrollTarget = null;
                                }
                            }
                            window.addEventListener('scrollend', onScrollEnd);
                            target.scrollIntoView({ behavior: 'smooth' });
                        }
                    });
                });
            }

            prevBtn.addEventListener('click', function() {
                if (currentIdx > 0) { currentIdx--; render(); }
            });
            nextBtn.addEventListener('click', function() {
                if (currentIdx < months.length - 1) { currentIdx++; render(); }
            });

            render();
        })();
