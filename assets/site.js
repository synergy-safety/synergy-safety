(function () {
  var DESKTOP_MQ = window.matchMedia('(min-width: 900px)');
  var HOVER_MQ = window.matchMedia('(hover: hover) and (pointer: fine)');

  function isDesktop() {
    return DESKTOP_MQ.matches;
  }

  function canHoverOpen() {
    return isDesktop() && HOVER_MQ.matches;
  }

  function setSubNavOpen(parent, btn, open) {
    if (!parent || !btn) return;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    parent.classList.toggle('is-sub-open', open);
    if (open) parent.classList.remove('is-sub-dismissed');
  }

  function closeSubNav(parent, btn, lockHover) {
    if (!parent || !btn) return;
    if (lockHover && canHoverOpen() && parent.matches(':hover')) {
      parent.classList.add('is-sub-dismissed');
    }
    setSubNavOpen(parent, btn, false);
  }

  function closeAllSubNavs(lockHover) {
    document.querySelectorAll('.nav-has-sub').forEach(function (parent) {
      closeSubNav(parent, parent.querySelector('.nav-sub-toggle'), lockHover);
    });
  }

  closeAllSubNavs(false);

  DESKTOP_MQ.addEventListener('change', function () {
    document.querySelectorAll('.nav-has-sub').forEach(function (parent) {
      parent.classList.remove('is-sub-dismissed');
    });
    closeAllSubNavs(false);
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
      if (!nextOpen) closeAllSubNavs(false);
    });
    nav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        toggle.setAttribute('aria-expanded', 'false');
        nav.classList.remove('is-open');
        document.body.classList.remove('nav-open');
        closeAllSubNavs(false);
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
            other.classList.remove('is-sub-dismissed');
            setSubNavOpen(other, other.querySelector('.nav-sub-toggle'), false);
          }
        });
        setSubNavOpen(parent, btn, true);
      } else {
        closeSubNav(parent, btn, true);
      }
    });

    parent.addEventListener('mouseenter', function () {
      if (!canHoverOpen()) return;
      if (parent.classList.contains('is-sub-dismissed')) return;
      setSubNavOpen(parent, btn, true);
    });

    parent.addEventListener('mouseleave', function () {
      if (!isDesktop()) return;
      window.setTimeout(function () {
        if (!parent.matches(':hover')) {
          parent.classList.remove('is-sub-dismissed');
          setSubNavOpen(parent, btn, false);
        }
      }, 80);
    });
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest('.nav-has-sub')) return;
    closeAllSubNavs(true);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    closeAllSubNavs(true);
    if (toggle && nav && toggle.getAttribute('aria-expanded') === 'true') {
      toggle.setAttribute('aria-expanded', 'false');
      nav.classList.remove('is-open');
      document.body.classList.remove('nav-open');
    }
  });

  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
})();
