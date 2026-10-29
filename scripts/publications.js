(() => {
  "use strict";

  // A direct link to a paper should reveal it even in the collapsed group.
  function revealLinkedPaper() {
    let id;
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch (_) {
      return;
    }
    if (!id) return;
    const target = document.getElementById(id);
    const group = target && target.closest("details.publication-group");
    if (!group) return;
    group.open = true;
    requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
  }

  revealLinkedPaper();
  window.addEventListener("hashchange", revealLinkedPaper);
})();
