(function () {
  'use strict';

  /* ---------- storage (may throw in private mode / blocked cookies) ---------- */
  var store = {
    get: function (k, fallback) {
      try {
        var v = localStorage.getItem(k);
        return v === null ? fallback : v;
      } catch (e) {
        return fallback;
      }
    },
    set: function (k, v) {
      try {
        localStorage.setItem(k, v);
      } catch (e) {}
    },
  };

  /* ---------- theme ---------- */
  var toggle = document.querySelector('.theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var explicit = document.documentElement.dataset.theme;
      var dark = explicit
        ? explicit === 'dark'
        : matchMedia('(prefers-color-scheme: dark)').matches;
      var next = dark ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      store.set('mba:theme', next);
    });
  }

  /* ---------- mobile drawer ---------- */
  var sidebar = document.getElementById('sidebar');
  var burger = document.querySelector('.hamburger');
  var backdrop = document.querySelector('.backdrop');
  function setDrawer(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (backdrop) backdrop.hidden = !open;
    if (burger) burger.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : '';
  }
  if (burger) burger.addEventListener('click', function () { setDrawer(!sidebar.classList.contains('is-open')); });
  if (backdrop) backdrop.addEventListener('click', function () { setDrawer(false); });

  /* ---------- Persian normalization ---------- */
  // Without this, a query typed with Arabic yeh/kaf ("بازاريابي") never matches
  // text stored with Persian yeh/kaf ("بازاریابی").
  function norm(s) {
    return String(s || '')
      .replace(/[يى]/g, 'ی')
      .replace(/ك/g, 'ک')
      .replace(/[أإآ]/g, 'ا')
      .replace(/ة/g, 'ه')
      .replace(/[ً-ْٰـ]/g, '')
      .replace(/[‌‏‎]/g, ' ')
      .replace(/[۰-۹]/g, function (d) { return String.fromCharCode(d.charCodeAt(0) - 0x06f0 + 48); })
      .replace(/[٠-٩]/g, function (d) { return String.fromCharCode(d.charCodeAt(0) - 0x0660 + 48); })
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  /* ---------- search ---------- */
  var input = document.getElementById('q');
  var results = document.getElementById('search-results');
  var index = null;
  var loading = false;

  function loadIndex() {
    if (index || loading) return Promise.resolve(index);
    loading = true;
    return fetch('/search-index.json')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        index = data.map(function (e) {
          return { u: e.u, t: e.t, c: e.c, hay: norm(e.t + ' ' + e.c + ' ' + e.k + ' ' + e.d), nt: norm(e.t) };
        });
        return index;
      })
      .catch(function () { index = []; return index; })
      .finally(function () { loading = false; });
  }

  function render(list, q) {
    if (!results) return;
    if (!q) { results.hidden = true; results.innerHTML = ''; return; }
    if (!list.length) {
      results.innerHTML = '<p class="search-empty">نتیجه‌ای یافت نشد.</p>';
      results.hidden = false;
      return;
    }
    results.innerHTML = list
      .slice(0, 12)
      .map(function (e) {
        return '<a href="' + e.u + '"><b>' + e.t + '</b>' + (e.c ? '<span>' + e.c + '</span>' : '') + '</a>';
      })
      .join('');
    results.hidden = false;
  }

  function search(raw) {
    var q = norm(raw);
    if (!q) return render([], '');
    loadIndex().then(function (data) {
      var terms = q.split(' ');
      var scored = [];
      for (var i = 0; i < data.length; i++) {
        var e = data[i], score = 0, ok = true;
        for (var j = 0; j < terms.length; j++) {
          var t = terms[j];
          if (e.nt.indexOf(t) === 0) score += 6;
          else if (e.nt.indexOf(t) > -1) score += 4;
          else if (e.hay.indexOf(t) > -1) score += 1;
          else { ok = false; break; }
        }
        if (ok) scored.push({ e: e, s: score });
      }
      scored.sort(function (a, b) { return b.s - a.s; });
      render(scored.map(function (x) { return x.e; }), q);
    });
  }

  if (input) {
    input.addEventListener('focus', loadIndex, { once: true });
    var timer;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var v = input.value;
      timer = setTimeout(function () { search(v); }, 90);
    });
    document.addEventListener('click', function (e) {
      if (results && !results.contains(e.target) && e.target !== input) results.hidden = true;
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== input && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault();
      if (input) input.focus();
    } else if (e.key === 'Escape') {
      if (results && !results.hidden) { results.hidden = true; if (input) input.blur(); }
      else setDrawer(false);
    }
  });

  /* ---------- read tracking ---------- */
  function readSet() {
    try { return new Set(JSON.parse(store.get('mba:read', '[]'))); } catch (e) { return new Set(); }
  }
  function saveRead(set) {
    store.set('mba:read', JSON.stringify(Array.from(set)));
  }

  var read = readSet();

  document.querySelectorAll('.nav-topics a[data-topic]').forEach(function (a) {
    if (read.has(a.dataset.topic)) a.classList.add('is-read');
  });

  var cards = document.querySelectorAll('.topic-cards li[data-topic]');
  function paintProgress() {
    var done = 0;
    cards.forEach(function (li) {
      var hit = read.has(li.dataset.topic);
      li.classList.toggle('is-read', hit);
      if (hit) done++;
    });
    var box = document.querySelector('.chapter-progress');
    if (box && cards.length) box.textContent = done + ' از ' + cards.length + ' مبحث خوانده شده';
  }
  if (cards.length) paintProgress();

  var btn = document.querySelector('.read-toggle');
  if (btn) {
    var url = btn.dataset.topic;
    var sync = function () {
      var on = read.has(url);
      btn.setAttribute('aria-pressed', String(on));
      btn.querySelector('.read-label').textContent = on ? 'خوانده شد' : 'علامت‌گذاری به‌عنوان خوانده‌شده';
    };
    sync();
    btn.addEventListener('click', function () {
      if (read.has(url)) read.delete(url); else read.add(url);
      saveRead(read);
      sync();
      var link = document.querySelector('.nav-topics a[data-topic="' + url + '"]');
      if (link) link.classList.toggle('is-read', read.has(url));
    });
  }
})();
