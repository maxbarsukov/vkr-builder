(function () {
  'use strict';

  var app = document.querySelector('.app');
  var canvas = document.querySelector('.canvas');
  var pages = Array.prototype.slice.call(document.querySelectorAll('.page'));

  var now = new Date();

  var year = document.getElementById('year');
  if (year) { year.textContent = String(now.getFullYear()); }

  var today = ('0' + now.getDate()).slice(-2) + '.' +
              ('0' + (now.getMonth() + 1)).slice(-2) + '.' +
              now.getFullYear();
  document.querySelectorAll('.today').forEach(function (el) {
    el.textContent = today;
  });

  var tabs = document.querySelectorAll('.tab[data-tab]');
  var panels = document.querySelectorAll('.ribbon-panel');

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.classList.toggle('is-active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      panels.forEach(function (p) {
        p.classList.toggle('is-active', p.dataset.panel === tab.dataset.tab);
      });
      ribbon.classList.remove('is-collapsed');
      ribbonToggle.setAttribute('aria-expanded', 'true');
    });
  });

  var ribbon = document.getElementById('ribbon');
  var ribbonToggle = document.querySelector('.ribbon-toggle');

  ribbonToggle.addEventListener('click', function () {
    var open = ribbon.classList.toggle('is-collapsed') === false;
    ribbonToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    ribbonToggle.title = open ? 'Свернуть ленту' : 'Развернуть ленту';
  });

  var toast = document.getElementById('toast');
  var toastTimer = null;

  function say(text) {
    toast.textContent = text;
    toast.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('is-on'); }, 3600);
  }

  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-toast]');
    if (el) { say(el.dataset.toast); }
  });

  var fsBtn = document.querySelector('[data-action="fullscreen"]');
  var closeBtn = document.querySelector('[data-action="close"]');

  function isFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function syncFullscreen() {
    var on = isFullscreen();
    var label = on ? 'Свернуть из полноэкранного режима' : 'Развернуть на весь экран';
    fsBtn.classList.toggle('is-full', on);
    fsBtn.title = label;
    fsBtn.setAttribute('aria-label', label);
  }

  if (fsBtn) {
    fsBtn.addEventListener('click', function () {
      var root = document.documentElement;
      var host = isFullscreen() ? document : root;
      var run = isFullscreen()
        ? (document.exitFullscreen || document.webkitExitFullscreen)
        : (root.requestFullscreen || root.webkitRequestFullscreen);
      if (!run) { say('Полноэкранный режим недоступен — попробуйте F11'); return; }

      var res = run.call(host);
      if (res && res.catch) {
        res.catch(function () { say('Полноэкранный режим недоступен — попробуйте F11'); });
      }
    });
    document.addEventListener('fullscreenchange', syncFullscreen);
    document.addEventListener('webkitfullscreenchange', syncFullscreen);
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      window.close();
      setTimeout(function () { say('Эту вкладку закрывает браузер: Ctrl+W, на macOS ⌘W'); }, 240);
    });
  }

  var markButtons = document.querySelectorAll('[data-action="marks"]');
  var marksOn = false;

  function setMarks(on) {
    marksOn = on;
    document.body.classList.toggle('marks', on);
    markButtons.forEach(function (b) { b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
    say(on ? 'Непечатаемые знаки: ¶ — конец абзаца'
           : 'Непечатаемые знаки выключены');
  }

  markButtons.forEach(function (b) {
    b.addEventListener('click', function () { setMarks(!marksOn); });
  });

  document.querySelectorAll('.copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var code = btn.parentElement.querySelector('code');
      var text = code ? code.innerText : '';
      var done = function () {
        btn.textContent = 'Скопировано';
        btn.classList.add('is-done');
        setTimeout(function () {
          btn.textContent = 'Копировать';
          btn.classList.remove('is-done');
        }, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { say('Скопировать не вышло: выделите текст вручную'); });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (err) { say('Скопировать не вышло: выделите текст вручную'); }
        document.body.removeChild(ta);
      }
    });
  });

  var stCur = document.getElementById('st-cur');
  var stTot = document.getElementById('st-tot');
  var stWords = document.getElementById('st-words');

  stTot.textContent = String(pages.length);

  var words = 0;
  pages.forEach(function (p) {
    var body = p.querySelector('.page-body');
    var m = (body.innerText || body.textContent || '').match(/[^\s]+/g);
    words += m ? m.length : 0;
  });
  stWords.textContent = words.toLocaleString('ru-RU');

  var ticking = false;
  function updatePage() {
    var off = parseFloat(getComputedStyle(document.documentElement)
      .getPropertyValue('--scroll-off')) || 60;
    var top = canvas.getBoundingClientRect().top + off + 34;
    var cur = 1;
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].getBoundingClientRect().top <= top) { cur = i + 1; }
    }
    stCur.textContent = String(cur);
    ticking = false;
  }
  canvas.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(updatePage); }
  }, { passive: true });
  updatePage();

  var zoom = 1;
  var zoomVal = document.getElementById('zoom-val');

  function setZoom(z) {
    zoom = Math.min(1.5, Math.max(0.6, Math.round(z * 10) / 10));
    app.style.setProperty('--zoom', String(zoom));
    zoomVal.textContent = Math.round(zoom * 100) + '%';
  }
  document.getElementById('zoom-in').addEventListener('click', function () { setZoom(zoom + 0.1); });
  document.getElementById('zoom-out').addEventListener('click', function () { setZoom(zoom - 0.1); });

  var selBox = null;

  function clearObject() {
    if (selBox) { selBox.remove(); selBox = null; }
  }

  function selectObject(el) {
    var page = el.closest('.page');
    if (!page) { return; }
    clearObject();

    var pr = page.getBoundingClientRect();
    var z = page.offsetWidth ? pr.width / page.offsetWidth : 1;
    var r = el.getBoundingClientRect();

    selBox = document.createElement('div');
    selBox.className = 'obj-sel';
    for (var i = 0; i < 8; i++) { selBox.appendChild(document.createElement('i')); }
    selBox.style.left = (r.left - pr.left) / z + 'px';
    selBox.style.top = (r.top - pr.top) / z + 'px';
    selBox.style.width = r.width / z + 'px';
    selBox.style.height = r.height / z + 'px';
    page.appendChild(selBox);
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('a, button, .chrome, .statusbar')) { return; }
    var obj = e.target.closest('.fig, .tbl-wrap, .listing');
    if (!obj) { clearObject(); return; }
    if (obj.classList.contains('fig')) {
      obj = obj.querySelector('svg:not([style*="none"])') || obj;
      var svgs = e.target.closest('.fig').querySelectorAll('svg');
      for (var i = 0; i < svgs.length; i++) {
        if (svgs[i].getClientRects().length) { obj = svgs[i]; break; }
      }
    }
    selectObject(obj);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { clearObject(); }
  });
  window.addEventListener('resize', clearObject);

  document.querySelectorAll('a[href^="http"]').forEach(function (a) {
    a.target = '_blank';
    a.rel = 'noopener';
  });

  var barTimer = null;

  function markTarget(el) {
    var page = el.closest('.page');
    if (!page || el === page) { return; }

    var last = el;
    var next = el.nextElementSibling;
    if ((el.classList.contains('lst-cap') || el.classList.contains('tbl-cap')) && next) {
      last = next;
    }

    var old = page.parentElement.querySelectorAll('.jump-bar');
    Array.prototype.forEach.call(old, function (b) { b.remove(); });

    var bar = document.createElement('div');
    bar.className = 'jump-bar';
    bar.style.top = el.offsetTop + 'px';
    bar.style.height = Math.max(12, last.offsetTop + last.offsetHeight - el.offsetTop) + 'px';
    page.appendChild(bar);

    clearTimeout(barTimer);
    barTimer = setTimeout(function () { bar.remove(); }, 2100);
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="#"]');
    if (!a) { return; }
    var id = a.getAttribute('href').slice(1);
    var el = document.getElementById(id);
    if (!el) { return; }
    e.preventDefault();
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(null, '', '#' + id);
    markTarget(el);
    if (!el.hasAttribute('tabindex')) { el.setAttribute('tabindex', '-1'); }
    el.focus({ preventScroll: true });
    setTimeout(updatePage, 400);
  });

})();
