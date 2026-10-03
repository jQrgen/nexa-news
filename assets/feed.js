// Client-side filters for the feed page. No tracking, no network calls; state lives in the URL hash.
(function () {
  var items = [].slice.call(document.querySelectorAll('#feed .item'));
  if (!items.length) return;
  var chips = [].slice.call(document.querySelectorAll('[data-platform]'));
  var segs = [].slice.call(document.querySelectorAll('[data-cat]'));
  var q = document.getElementById('q'), count = document.getElementById('count');
  function chosen() { return chips.filter(function (c) { return c.getAttribute('aria-pressed') === 'true'; }).map(function (c) { return c.dataset.platform; }); }
  function cat() { var s = segs.filter(function (b) { return b.getAttribute('aria-pressed') === 'true'; })[0]; return s ? s.dataset.cat : ''; }
  function apply(save) {
    var p = chosen(), c = cat(), text = (q.value || '').trim().toLowerCase(), n = 0;
    items.forEach(function (li) {
      var ok = (!p.length || p.indexOf(li.dataset.p) >= 0) && (!c || li.dataset.c === c) && (!text || li.textContent.toLowerCase().indexOf(text) >= 0);
      li.hidden = !ok; if (ok) n++;
    });
    count.textContent = n + (n === 1 ? ' item' : ' items');
    if (save) {
      var h = new URLSearchParams();
      if (p.length) h.set('platform', p.join(',')); if (c) h.set('category', c); if (text) h.set('q', text);
      history.replaceState(null, '', h.toString() ? '#' + h.toString() : location.pathname + location.search);
    }
  }
  var h = new URLSearchParams(location.hash.slice(1));
  (h.get('platform') || '').split(',').forEach(function (x) { chips.forEach(function (c) { if (c.dataset.platform === x) c.setAttribute('aria-pressed', 'true'); }); });
  if (h.get('category')) segs.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.cat === h.get('category') ? 'true' : 'false'); });
  if (h.get('q')) q.value = h.get('q');
  chips.forEach(function (c) { c.addEventListener('click', function () { c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply(true); }); });
  segs.forEach(function (b) { b.addEventListener('click', function () { segs.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); }); apply(true); }); });
  q.addEventListener('input', function () { apply(true); });
  window.addEventListener('hashchange', function () { location.reload(); });
  apply(false);
})();
