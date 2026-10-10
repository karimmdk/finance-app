/*
 * کشوی منو + نوار بالا برای نسخه اندروید. روی همان DOM اپ React کار می‌کند و به کد اپ دست نمی‌زند.
 * نوار بالا و کشو فقط وقتی دیده می‌شوند که mobile.css (media query) فعال باشد.
 */
(function () {
  'use strict';
  var root = document.documentElement;

  function isOpen() { return root.classList.contains('fa-nav-open'); }
  function setOpen(v) { root.classList.toggle('fa-nav-open', !!v); }

  // برای دکمه Back اندروید (Kotlin صدا می‌زند): true یعنی خودم مصرفش کردم
  window.faBack = function () {
    if (window.faCloseSheet && window.faCloseSheet()) return true;   // پنجره‌های ویرایش/حذف
    if (isOpen()) { setOpen(false); return true; }
    var btns = document.querySelectorAll('aside nav button');
    if (btns.length && String(btns[0].className).indexOf('bg-indigo-50') === -1) {
      btns[0].click();           // از هر صفحه‌ای اول به «داشبورد» برگرد
      return true;
    }
    return false;
  };

  var ICON_MENU = '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  var ICON_MORE = '<svg viewBox="0 0 24 24"><circle class="dot" cx="12" cy="5" r="2"/><circle class="dot" cx="12" cy="12" r="2"/><circle class="dot" cx="12" cy="19" r="2"/></svg>';

  function build() {
    if (document.getElementById('fa-topbar')) return;
    var bar = document.createElement('div');
    bar.id = 'fa-topbar';
    bar.innerHTML =
      '<button id="fa-menu-btn" type="button" aria-label="منو">' + ICON_MENU + '</button>' +
      '<div id="fa-title"></div>' +
      (window.AndroidBridge ? '<button id="fa-more-btn" type="button" aria-label="گزینه‌ها">' + ICON_MORE + '</button>' : '');
    document.body.insertBefore(bar, document.getElementById('root'));

    var scrim = document.createElement('div');
    scrim.id = 'fa-scrim';
    document.body.appendChild(scrim);

    document.getElementById('fa-menu-btn').addEventListener('click', function () { setOpen(!isOpen()); });
    scrim.addEventListener('click', function () { setOpen(false); });
    var more = document.getElementById('fa-more-btn');
    if (more) more.addEventListener('click', function () { window.AndroidBridge.showMenu(); });

    // انتخاب یک آیتم منو: کشو بسته شود و صفحه جدید از بالا شروع شود
    document.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('aside nav button')) {
        setOpen(false);
        setTimeout(function () {
          var m = document.querySelector('main');
          if (m) m.scrollTop = 0;
        }, 0);
      }
    });

    var title = document.getElementById('fa-title');
    var queued = false;
    function syncTitle() {
      queued = false;
      var b = document.querySelector('aside nav button[class*="bg-indigo-50"]');
      var label = b && b.querySelector('span:last-child');
      title.textContent = label ? label.textContent : 'مدیریت مالی شخصی';
    }
    new MutationObserver(function () {
      if (!queued) { queued = true; requestAnimationFrame(syncTitle); }
    }).observe(document.getElementById('root'), {
      subtree: true, childList: true, attributes: true, attributeFilter: ['class']
    });
    syncTitle();
  }

  // کشیدن لبه‌ی سربرگ ستون برای تغییر عرض: اپ فقط رویداد ماوس را می‌فهمد؛ لمس را به همان تبدیل می‌کنیم.
  // نکته: اپ بعد از هر تغییر عرض، دستگیره‌ها را از نو می‌سازد و عنصری که انگشت رویش است از DOM حذف می‌شود؛
  // رویدادهای لمسی همیشه به همان عنصرِ شروع می‌روند، پس شنونده‌ها را مستقیم روی خود آن عنصر می‌گذاریم.
  (function resizeByTouch() {
    function fire(type, pt, target) {
      target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, button: 0, clientX: pt.clientX, clientY: pt.clientY }));
    }
    document.addEventListener('touchstart', function (e) {
      var handle = e.target.closest && e.target.closest('.cursor-col-resize');
      if (!handle || !e.touches.length) return;
      e.preventDefault();
      fire('mousedown', e.touches[0], handle);
      function move(ev) {
        ev.preventDefault();
        if (ev.touches.length) fire('mousemove', ev.touches[0], window);
      }
      function end(ev) {
        handle.removeEventListener('touchmove', move);
        handle.removeEventListener('touchend', end);
        handle.removeEventListener('touchcancel', end);
        var pt = (ev.changedTouches && ev.changedTouches[0]) || { clientX: 0, clientY: 0 };
        fire('mouseup', pt, window);
      }
      handle.addEventListener('touchmove', move, { passive: false });
      handle.addEventListener('touchend', end);
      handle.addEventListener('touchcancel', end);
    }, { passive: false });
  })();

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
