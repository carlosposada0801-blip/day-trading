// Applied in <head> before the page paints, so there's no flash of the wrong theme.
(function () {
  try {
    var t = localStorage.getItem("theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: follow the system setting */ }
})();
