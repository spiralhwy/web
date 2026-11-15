{# Sticky date headers: show the back-to-top button once past the page header, and flash the header that becomes stuck. Expects .sticky-wrapper elements and a #top header. `scrollTarget` is shared with calendar.js. #}
            const header = document.getElementById('top');
            const wrappers = document.querySelectorAll('.sticky-wrapper');
            const headerObserver = new IntersectionObserver(([entry]) => {
                const pastHeader = !entry.isIntersecting;
                wrappers.forEach(w => w.classList.toggle('past-header', pastHeader));
            });
            headerObserver.observe(header);

            let currentStuck = null;
            let scrollTarget = null;
            const stickyObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    entry.target.classList.toggle('stuck', entry.intersectionRatio < 1);
                });
            }, { threshold: 1, rootMargin: '-1px 0px 0px 0px' });
            wrappers.forEach(w => stickyObserver.observe(w));

            window.addEventListener('scroll', function() {
                // The visible sticky header is the last shown wrapper (in DOM order)
                // that has reached the viewport top: every passed wrapper stays stuck
                // at top 0, the rest sit below. Don't compare offsetTop to scrollY:
                // a stuck element's offsetTop tracks its stuck spot, rounded to whole
                // pixels, so on fractional scroll positions (hi-DPI, zoom, trackpads)
                // it flickers past scrollY and re-flashes the same header.
                let active = null;
                wrappers.forEach(w => {
                    if (w.style.display !== 'none' && w.getBoundingClientRect().top <= 1) {
                        active = w;
                    }
                });
                if (!active) {
                    currentStuck = null;
                } else if (active !== currentStuck) {
                    currentStuck = active;
                    if (!scrollTarget) {
                        active.classList.remove('flash');
                        void active.offsetWidth;
                        active.classList.add('flash');
                    }
                }
            });

            document.querySelectorAll('.top-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    scrollTarget = true; // suppress flash during scroll
                    window.addEventListener('scrollend', function clear() {
                        window.removeEventListener('scrollend', clear);
                        scrollTarget = null;
                    });
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                });
            });
