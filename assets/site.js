(function () {
  var DESKTOP_MQ = window.matchMedia('(min-width: 900px)');

  function isDesktop() {
    return DESKTOP_MQ.matches;
  }

  function setSubNavOpen(parent, btn, open) {
    if (!parent || !btn) return;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    parent.classList.toggle('is-sub-open', open);
  }

  function closeAllSubNavs() {
    document.querySelectorAll('.nav-has-sub').forEach(function (parent) {
      var btn = parent.querySelector('.nav-sub-toggle');
      setSubNavOpen(parent, btn, false);
    });
  }

  function applyMobileDefaultSubnav() {
    if (isDesktop()) return;
    document.querySelectorAll('.nav-has-sub[data-subnav-default-open="1"]').forEach(function (parent) {
      var btn = parent.querySelector('.nav-sub-toggle');
      setSubNavOpen(parent, btn, true);
    });
  }

  function applyDesktopSubnavState() {
    if (!isDesktop()) return;
    closeAllSubNavs();
  }

  document.querySelectorAll('.nav-has-sub').forEach(function (parent) {
    if (parent.classList.contains('is-sub-open')) {
      parent.dataset.subnavDefaultOpen = '1';
    }
  });

  applyDesktopSubnavState();
  DESKTOP_MQ.addEventListener('change', function () {
    if (isDesktop()) {
      applyDesktopSubnavState();
    } else {
      applyMobileDefaultSubnav();
    }
  });

  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = toggle.getAttribute('aria-expanded') === 'true';
      var nextOpen = !open;
      toggle.setAttribute('aria-expanded', String(nextOpen));
      nav.classList.toggle('is-open', nextOpen);
      document.body.classList.toggle('nav-open', nextOpen);
      if (nextOpen) {
        applyMobileDefaultSubnav();
      } else {
        closeAllSubNavs();
      }
    });
    nav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        toggle.setAttribute('aria-expanded', 'false');
        nav.classList.remove('is-open');
        document.body.classList.remove('nav-open');
        closeAllSubNavs();
      });
    });
  }

  document.querySelectorAll('.nav-sub-toggle').forEach(function (btn) {
    var parent = btn.closest('.nav-has-sub');
    var submenuId = btn.getAttribute('aria-controls');
    var submenu = submenuId ? document.getElementById(submenuId) : null;
    if (!parent || !submenu) return;

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var open = btn.getAttribute('aria-expanded') === 'true';
      if (!open) {
        document.querySelectorAll('.nav-has-sub').forEach(function (other) {
          if (other !== parent) {
            setSubNavOpen(other, other.querySelector('.nav-sub-toggle'), false);
          }
        });
      }
      setSubNavOpen(parent, btn, !open);
    });

    parent.addEventListener('mouseleave', function () {
      if (!isDesktop()) return;
      window.setTimeout(function () {
        if (!parent.matches(':hover')) {
          setSubNavOpen(parent, btn, false);
        }
      }, 80);
    });
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest('.nav-has-sub')) return;
    closeAllSubNavs();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    closeAllSubNavs();
    if (toggle && nav && toggle.getAttribute('aria-expanded') === 'true') {
      toggle.setAttribute('aria-expanded', 'false');
      nav.classList.remove('is-open');
      document.body.classList.remove('nav-open');
    }
  });

  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
