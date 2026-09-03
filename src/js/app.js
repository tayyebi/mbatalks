(function () {
  'use strict';

  var doc = document;
  function $(sel, root) { return (root || doc).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || doc).querySelectorAll(sel));
  }

  var FA = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  function faNum(n) {
    return String(n).replace(/\d/g, function (d) { return FA[+d]; });
  }

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
  var toggle = $('.theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var explicit = doc.documentElement.dataset.theme;
      var dark = explicit
        ? explicit === 'dark'
        : matchMedia('(prefers-color-scheme: dark)').matches;
      var next = dark ? 'light' : 'dark';
      doc.documentElement.dataset.theme = next;
      store.set('mba:theme', next);
    });
  }

  /* ---------- mobile drawer ---------- */
  var sidebar = $('#sidebar');
  var burger = $('.hamburger');
  var backdrop = $('.backdrop');

  function drawerOpen() {
    return !!sidebar && sidebar.classList.contains('is-open');
  }
  function setDrawer(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (backdrop) backdrop.hidden = !open;
    if (burger) burger.setAttribute('aria-expanded', String(open));
    doc.body.style.overflow = open ? 'hidden' : '';
    if (open) {
      var first = sidebar.querySelector('[aria-current]') || sidebar.querySelector('a');
      if (first) first.focus({ preventScroll: true });
    } else if (sidebar.contains(doc.activeElement) && burger) {
      burger.focus();
    }
  }
  if (burger) burger.addEventListener('click', function () { setDrawer(!drawerOpen()); });
  if (backdrop) backdrop.addEventListener('click', function () { setDrawer(false); });
  var drawerClose = $('.drawer-close');
  if (drawerClose) drawerClose.addEventListener('click', function () { setDrawer(false); });

  // Keep the current page visible in a long table of contents.
  if (sidebar) {
    var current = sidebar.querySelector('[aria-current]');
    if (current) {
      var y = current.offsetTop - sidebar.clientHeight / 2;
      if (y > 0) sidebar.scrollTop = y;
    }
  }

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
  var topbar = $('#topbar');
  var input = $('#q');
  var results = $('#search-results');
  var searchToggle = $('.search-toggle');
  var searchClose = $('.search-close');
  var index = null;
  var loading = false;

  // Below 720px the field is folded away behind a button; above it is always there.
  function setSearch(open) {
    if (!topbar) return;
    topbar.classList.toggle('is-searching', open);
    if (searchToggle) searchToggle.setAttribute('aria-expanded', String(open));
    if (open) {
      if (input) input.focus();
    } else if (results) {
      results.hidden = true;
    }
  }
  if (searchToggle) searchToggle.addEventListener('click', function () { setSearch(true); });
  if (searchClose) {
    searchClose.addEventListener('click', function () {
      if (input) input.value = '';
      setSearch(false);
      if (searchToggle) searchToggle.focus();
    });
  }

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

  // Arrow keys walk the result list so the whole search works without a mouse.
  function moveActive(step) {
    if (!results || results.hidden) return false;
    var links = $$('a', results);
    if (!links.length) return false;
    var at = links.indexOf($('a.is-active', results));
    var next = at + step;
    if (next < 0) next = links.length - 1;
    if (next >= links.length) next = 0;
    links.forEach(function (a) { a.classList.remove('is-active'); });
    links[next].classList.add('is-active');
    links[next].scrollIntoView({ block: 'nearest' });
    return true;
  }

  if (input) {
    input.addEventListener('focus', loadIndex, { once: true });
    var timer;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var v = input.value;
      timer = setTimeout(function () { search(v); }, 90);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' && moveActive(1)) e.preventDefault();
      else if (e.key === 'ArrowUp' && moveActive(-1)) e.preventDefault();
      else if (e.key === 'Enter') {
        var active = results && $('a.is-active', results);
        if (active) { e.preventDefault(); location.href = active.href; }
      }
    });
    doc.addEventListener('click', function (e) {
      if (results && !results.contains(e.target) && e.target !== input) results.hidden = true;
      // A tap outside the bar folds the phone-sized search away again.
      if (topbar && topbar.classList.contains('is-searching') && !topbar.contains(e.target)) {
        setSearch(false);
      }
    });
  }

  /* ---------- keyboard ---------- */
  function typing() {
    var el = doc.activeElement;
    return !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
  }

  doc.addEventListener('keydown', function (e) {
    if (e.key === '/' && !typing()) {
      e.preventDefault();
      setSearch(true);
      if (input) input.focus();
      return;
    }
    if (e.key === 'Escape') {
      if (results && !results.hidden) { results.hidden = true; if (input) input.blur(); }
      else if (topbar && topbar.classList.contains('is-searching')) setSearch(false);
      else setDrawer(false);
      return;
    }
    // Page through the book with the arrow keys — mirrored, since the text is RTL.
    if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight')
        && !typing() && !drawerOpen()
        && !(e.altKey || e.ctrlKey || e.metaKey || e.shiftKey)) {
      var rel = e.key === 'ArrowLeft' ? 'next' : 'prev';
      var link = $('.pager a[rel="' + rel + '"]');
      if (link) { e.preventDefault(); location.href = link.href; }
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
  var btn = $('.read-toggle');
  var url = btn && btn.dataset.topic;

  function setMeter(el, done, total) {
    if (el) el.style.width = (total ? Math.round((done / total) * 100) : 0) + '%';
  }

  // Read topics are stored as their URL, so a chapter's tally is a prefix match.
  function countIn(prefix) {
    var n = 0;
    read.forEach(function (u) { if (u.indexOf(prefix) === 0) n++; });
    return n;
  }

  function paint() {
    $$('.nav-topics a[data-topic]').forEach(function (a) {
      a.classList.toggle('is-read', read.has(a.dataset.topic));
    });

    $$('.nav-chapter-link[data-chapter]').forEach(function (a) {
      var total = +a.dataset.topics || 0;
      var meter = a.parentNode.querySelector('.meter i');
      setMeter(meter, Math.min(countIn(a.dataset.chapter), total), total);
    });

    var book = $('.book-progress');
    if (book) {
      var total = +book.dataset.total || 0;
      var done = Math.min(read.size, total);
      var label = $('.book-progress-count', book);
      if (label) label.textContent = faNum(done) + ' از ' + faNum(total) + ' مبحث';
      setMeter($('.meter i', book), done, total);
    }

    var box = $('.chapter-progress');
    if (box) {
      var chTotal = +box.dataset.topics || 0;
      var chDone = 0;
      $$('.topic-cards li[data-topic]').forEach(function (li) {
        var hit = read.has(li.dataset.topic);
        li.classList.toggle('is-read', hit);
        if (hit) chDone++;
      });
      var chLabel = $('.chapter-progress-label', box);
      if (chLabel) {
        chLabel.textContent = faNum(chDone) + ' از ' + faNum(chTotal) + ' مبحث خوانده شده';
      }
      setMeter($('.meter i', box), chDone, chTotal);
    }

    if (btn) {
      var on = read.has(url);
      btn.setAttribute('aria-pressed', String(on));
      $('.read-label', btn).textContent = on ? 'خوانده شد' : 'علامت‌گذاری به‌عنوان خوانده‌شده';
    }
  }

  function setRead(on) {
    if (!url) return;
    if (on) read.add(url); else read.delete(url);
    saveRead(read);
    paint();
  }

  if (btn) {
    btn.addEventListener('click', function () { setRead(!read.has(url)); });
    // Remember where the reader was, for the "continue" card on the home page.
    store.set('mba:last', JSON.stringify({ u: url, t: btn.dataset.title || doc.title }));
  }
  paint();

  /* ---------- continue reading ---------- */
  var resume = $('#resume');
  if (resume) {
    var last = null;
    try { last = JSON.parse(store.get('mba:last', 'null')); } catch (e) {}
    if (last && last.u && last.t) {
      var lead = doc.createElement('span');
      lead.textContent = 'ادامه مطالعه:';
      var link = doc.createElement('a');
      link.href = last.u;
      link.textContent = last.t; // textContent, never innerHTML: this came from storage
      resume.appendChild(lead);
      resume.appendChild(link);
      resume.hidden = false;
    }
  }

  /* ---------- reading progress ---------- */
  var bar = $('.progress i');
  var article = $('.prose');
  var toTop = $('.to-top');
  if (toTop) {
    toTop.addEventListener('click', function () {
      scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
  if (bar && article) {
    var ticking = false;
    var autoMarked = false;

    var measure = function () {
      if (toTop) toTop.hidden = scrollY < 600;
      var box = article.getBoundingClientRect();
      var top = box.top + scrollY;
      var span = box.height - innerHeight;
      // A page that fits on one screen has nothing to track.
      if (span < 200) { bar.style.transform = 'scaleX(0)'; return; }
      var ratio = (scrollY - top) / span;
      ratio = ratio < 0 ? 0 : ratio > 1 ? 1 : ratio;
      bar.style.transform = 'scaleX(' + ratio.toFixed(4) + ')';
      // Reaching the end of the text is the honest signal that it was read.
      if (ratio > 0.96 && !autoMarked && url && !read.has(url)) {
        autoMarked = true;
        setRead(true);
      }
    };

    var onScroll = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; measure(); });
    };
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('resize', onScroll, { passive: true });
    measure();
  }

  /* ---------- keep scrolling to reach the next topic ---------- */
  // At the foot of the page the scroll has nowhere to go; that leftover push
  // fills the pill and then follows the "next" link, so the book can be read
  // straight through without reaching for a button.
  var panel = $('.continue');
  var nextLink = $('.pager a[rel="next"]');
  if (panel && nextLink) {
    var fill = $('.meter i', panel);
    var PULL = 220;      // how much leftover scrolling counts as "yes, go on"
    var SETTLE = 300;    // ignore the tail of the fling that reached the bottom
    var pulled = 0;
    var going = false;
    var bottomAt = 0;
    var idle;

    function atBottom() {
      return innerHeight + scrollY >= doc.documentElement.scrollHeight - 2;
    }
    function paintPull() {
      fill.style.width = Math.round((pulled / PULL) * 100) + '%';
    }
    function release() {
      pulled = 0;
      paintPull();
      panel.classList.remove('is-on');
      setTimeout(function () { if (!pulled) panel.hidden = true; }, 200);
    }
    function push(px) {
      if (going || drawerOpen()) return;
      if (!atBottom()) { bottomAt = 0; return; }
      var now = Date.now();
      if (!bottomAt) { bottomAt = now; return; }
      if (now - bottomAt < SETTLE) return;
      pulled = Math.min(PULL, pulled + px);
      panel.hidden = false;
      // reading the offset forces the layout that makes the transition run
      void panel.offsetWidth;
      panel.classList.add('is-on');
      paintPull();
      clearTimeout(idle);
      if (pulled >= PULL) {
        going = true;
        location.href = nextLink.href;
        return;
      }
      idle = setTimeout(release, 600);
    }

    addEventListener('wheel', function (e) {
      if (e.deltaY > 0) push(e.deltaY * 0.7);
    }, { passive: true });

    var touchY = null;
    addEventListener('touchstart', function (e) {
      touchY = e.touches[0].clientY;
    }, { passive: true });
    addEventListener('touchmove', function (e) {
      if (touchY === null) return;
      var y = e.touches[0].clientY;
      var dy = touchY - y; // positive while swiping the content upwards
      touchY = y;
      if (dy > 0) push(dy);
    }, { passive: true });
    addEventListener('touchend', function () {
      touchY = null;
      if (!going) release();
    }, { passive: true });
  }
})();
