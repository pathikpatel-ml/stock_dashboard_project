// Client-side filter and sort for mobile signal cards.
// Reads data-filter on active chip and value of #mobile-sort-select.
// Re-runs via MutationObserver after Dash replaces #v20-mobile-cards content.

(function () {
  var CARDS_ID = 'v20-mobile-cards';
  var STRENGTH_ORDER = {
    'STRONG BUY': 0,
    'BUY NOW':    1,
    'BUY':        2,
    'NEUTRAL':    3,
    'OVERBOUGHT': 4,
  };

  function runFilterSort() {
    var container = document.getElementById(CARDS_ID);
    if (!container) return;

    var activeChip = document.querySelector('.filter-chip.active');
    var filterVal = activeChip ? (activeChip.getAttribute('data-filter') || 'all') : 'all';

    var sortEl = document.getElementById('mobile-sort-select');
    var sortVal = sortEl ? sortEl.value : 'proximity';

    var cards = Array.from(container.querySelectorAll('.signal-card'));

    // Filter
    cards.forEach(function (card) {
      var sig = (card.getAttribute('data-signal') || '').toUpperCase();
      var show = true;
      if (filterVal === 'strong') {
        show = sig === 'STRONG BUY';
      } else if (filterVal === 'buy') {
        show = sig === 'STRONG BUY' || sig === 'BUY NOW' || sig === 'BUY';
      }
      card.style.display = show ? '' : 'none';
    });

    // Sort visible cards
    var visible = cards.filter(function (c) { return c.style.display !== 'none'; });
    visible.sort(function (a, b) {
      if (sortVal === 'symbol') {
        return (a.getAttribute('data-symbol') || '').localeCompare(b.getAttribute('data-symbol') || '');
      }
      if (sortVal === 'strength') {
        var ao = (STRENGTH_ORDER[a.getAttribute('data-signal')] !== undefined)
                   ? STRENGTH_ORDER[a.getAttribute('data-signal')] : 99;
        var bo = (STRENGTH_ORDER[b.getAttribute('data-signal')] !== undefined)
                   ? STRENGTH_ORDER[b.getAttribute('data-signal')] : 99;
        return ao - bo;
      }
      // Default: proximity ascending (closest to buy target first)
      return parseFloat(a.getAttribute('data-proximity') || '999') -
             parseFloat(b.getAttribute('data-proximity') || '999');
    });
    visible.forEach(function (c) { container.appendChild(c); });
  }

  // Filter chip clicks
  document.addEventListener('click', function (e) {
    var chip = e.target.closest('.filter-chip');
    if (!chip) return;
    document.querySelectorAll('.filter-chip').forEach(function (c) { c.classList.remove('active'); });
    chip.classList.add('active');
    runFilterSort();
  });

  // Sort select change
  document.addEventListener('change', function (e) {
    if (e.target.id === 'mobile-sort-select') runFilterSort();
  });

  // Re-run after Dash updates the cards container
  var cardObserver = new MutationObserver(function () { runFilterSort(); });

  function observeCards() {
    var c = document.getElementById(CARDS_ID);
    if (c) {
      cardObserver.disconnect();
      cardObserver.observe(c, { childList: true });
    }
  }

  // Watch for Dash replacing the container itself
  new MutationObserver(function () { observeCards(); })
    .observe(document.body, { childList: true, subtree: true });

  document.addEventListener('DOMContentLoaded', observeCards);
})();
