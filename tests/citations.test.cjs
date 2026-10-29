const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const code = readFileSync(path.join(__dirname, "../scripts/citations.js"), "utf8");

function snapshot(count = 3, updated = "2026-10-29T01:00:00Z") {
  return {
    schema_version: 1, profile_id: "01Pcm-AAAAAJ", updated_at: updated,
    publications: { paper: { title: "Test Paper", citations: count, checked_at: updated, status: "ok", citation_url: "https://scholar.google.com/scholar?cites=123" } },
  };
}

async function render(bundled, remote, fail = false) {
  const link = { dataset: { citationId: "paper" }, textContent: "Citation: —", href: "original", setAttribute(name, value) { this[name] = value; } };
  const context = { window: { SCHOLAR_CITATIONS: bundled }, document: { querySelectorAll: () => [link] }, URL, AbortController, setTimeout, clearTimeout,
    fetch: async () => { if (fail) throw new Error("offline"); return { ok: true, json: async () => remote }; },
  };
  vm.runInNewContext(code, context);
  await new Promise(resolve => setImmediate(resolve));
  return { link };
}

test("renders the bundled count and refreshes from newer remote data", async () => {
  const { link } = await render(snapshot(), snapshot(6, "2026-10-30T01:00:00Z"));
  assert.equal(link.textContent, "Citation: 6");
  assert.match(link.title, /Oct 30, 2026/);
  assert.match(link["aria-label"], /Test Paper: 6 citations/);
});

test("offline or older remote data preserves the bundled count", async () => {
  assert.equal((await render(snapshot(), null, true)).link.textContent, "Citation: 3");
  assert.equal((await render(snapshot(), snapshot(1, "2026-10-28T01:00:00Z"))).link.textContent, "Citation: 3");
});

test("zero is displayed but unknown counts are not converted to zero", async () => {
  assert.equal((await render(snapshot(0), null, true)).link.textContent, "Citation: 0");
  assert.equal((await render(snapshot(null), null, true)).link.textContent, "Citation: —");
});

test("rejects unrelated profiles and unsafe link destinations", async () => {
  const wrong = snapshot(99);
  wrong.profile_id = "someone-else";
  assert.equal((await render(snapshot(), wrong)).link.textContent, "Citation: 3");
  const unsafe = snapshot(99);
  unsafe.publications.paper.citation_url = "javascript:alert(1)";
  assert.equal((await render(snapshot(), unsafe)).link.textContent, "Citation: 3");
});
