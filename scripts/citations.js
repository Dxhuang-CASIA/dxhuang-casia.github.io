(() => {
  "use strict";
  const profileId = "01Pcm-AAAAAJ";
  const links = document.querySelectorAll("a.citation-count[data-citation-id]");
  let latestTimestamp = 0;

  function display(snapshot) {
    if (!snapshot || snapshot.schema_version !== 1 || snapshot.profile_id !== profileId) return;
    const timestamp = Date.parse(snapshot.updated_at);
    if (!Number.isFinite(timestamp) || timestamp < latestTimestamp || !snapshot.publications) return;
    let shown = 0;
    links.forEach((link) => {
      const paper = snapshot.publications[link.dataset.citationId];
      if (!paper || !Number.isInteger(paper.citations) || paper.citations < 0) return;
      const checked = new Date(paper.checked_at);
      if (!paper.checked_at || !Number.isFinite(checked.getTime())) return;
      let destination;
      try {
        destination = new URL(paper.citation_url);
      } catch (_) {
        return;
      }
      if (destination.protocol !== "https:" || destination.host !== "scholar.google.com") return;
      const count = paper.citations.toLocaleString("en-US");
      const date = checked.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
      link.textContent = `Citation: ${count}`;
      link.href = destination.href;
      link.title = `Google Scholar · Last checked ${date}${paper.status === "stale" ? " (using the last confirmed count)" : ""}`;
      link.setAttribute("aria-label", `${paper.title}: ${count} citations on Google Scholar`);
      shown += 1;
    });
    if (shown) {
      latestTimestamp = timestamp;
    }
  }

  display(window.SCHOLAR_CITATIONS);

  // Read the latest generated data directly: bot commits do not rebuild Pages.
  // Keep the bundled snapshot if GitHub is unavailable or the request times out.
  if (typeof fetch !== "function" || typeof AbortController !== "function") return;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  fetch("https://raw.githubusercontent.com/Dxhuang-CASIA/dxhuang-casia.github.io/main/data/scholar-citations.json", {
    cache: "no-store", signal: controller.signal, referrerPolicy: "no-referrer",
  }).then((response) => {
    if (!response.ok) throw new Error("Citation data unavailable");
    return response.json();
  }).then(display).catch(() => {
    // Existing counts and their last-checked dates remain visible.
  }).finally(() => clearTimeout(timeout));
})();
