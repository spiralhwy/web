{# After a filter hides blocks, fix up one date's header, dividers and trailing spacing: the header and spacing show only if some block is visible, and a divider shows only between two visible blocks. `blockClass` is the class of the listing blocks. #}
        function tidyDate(wrapper, blockClass) {
            const items = [];
            let sibling = wrapper.nextElementSibling;
            while (sibling && !sibling.classList.contains('sticky-wrapper') && sibling.tagName !== 'SCRIPT') {
                items.push(sibling);
                sibling = sibling.nextElementSibling;
            }
            function isVisibleBlock(el) {
                return el.classList.contains(blockClass) && el.style.display !== 'none';
            }
            const anyVisible = items.some(isVisibleBlock);
            wrapper.style.display = anyVisible ? '' : 'none';

            let blockAbove = false;  // a visible block since the last shown divider
            items.forEach(function(el, i) {
                if (el.classList.contains(blockClass)) {
                    blockAbove = blockAbove || isVisibleBlock(el);
                } else if (el.classList.contains('divider')) {
                    const show = blockAbove && items.slice(i + 1).some(isVisibleBlock);
                    el.style.display = show ? '' : 'none';
                    if (show) blockAbove = false;
                } else {
                    el.style.display = anyVisible ? '' : 'none';
                }
            });
        }
