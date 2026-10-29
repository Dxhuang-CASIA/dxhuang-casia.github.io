import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_citations import Document, build_snapshot, fetch_profile, normalize, parse_profile

PROFILE = "example"
STAMP = "2026-10-29T01:00:00Z"
CONFIG = {"profile_id": PROFILE, "publications": [{"id": "test", "title": "Test Paper", "scholar_id": "example:one"}]}


def row(title="Test Paper", count="12", key="one", include_count=True):
    count_cell = '<td><a class="gsc_a_ac" href="/scholar?cites=123">' + count + '</a></td>' if include_count else ""
    return ('<tr class="gsc_a_tr"><td><a class="gsc_a_at" href="/citations?citation_for_view=example:'
            + key + '">' + title + '</a></td>' + count_cell + '</tr>')


def page(*rows, more=False):
    return '<table>' + ''.join(rows) + '</table><button id="gsc_bpf_next"' + ('' if more else ' disabled') + '></button>'


class ParseTests(unittest.TestCase):
    def test_counts_zero_and_superscripts(self):
        html = page(row(count="1,234*"), row('C <svg aria-label="^ 2"></svg> LUE', count="", key="two"))
        records, more = parse_profile(html, PROFILE)
        self.assertEqual([r["citations"] for r in records], [1234, 0])
        self.assertEqual(normalize(records[1]["title"]), "c2lue")
        self.assertFalse(more)
        self.assertEqual(records[0]["citation_url"], "https://scholar.google.com/scholar?cites=123")

    def test_blocked_or_incomplete_pages_fail(self):
        for html in ['<html>CAPTCHA</html>', page(row(include_count=False)), page(row(count="Unavailable"))]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_profile(html, PROFILE)
        with self.assertRaises(ValueError):
            parse_profile(page(row()), "someone-else")

    def test_zero_without_cited_by_link_uses_article(self):
        records, _ = parse_profile(page(row(count="").replace('href="/scholar?cites=123"', 'href=""')), PROFILE)
        self.assertIn("view_citation", records[0]["citation_url"])
        self.assertEqual(records[0]["citations"], 0)

    def test_pagination(self):
        class Response:
            def __init__(self, html): self.html = html
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return self.html.encode()
        with patch("sync_citations.urlopen", side_effect=[Response(page(row(), more=True)), Response(page(row(key="two")))]) as fetch:
            records = fetch_profile(PROFILE)
            self.assertEqual(len(records), 2)
            self.assertIn("cstart=100", fetch.call_args.args[0].full_url)


class MatchingTests(unittest.TestCase):
    def test_counts_can_decrease_and_ids_survive_title_changes(self):
        records, _ = parse_profile(page(row()), PROFILE)
        previous = build_snapshot(CONFIG, records, {}, STAMP)
        records[0].update(title="Revised Title", citations=0)
        current = build_snapshot(CONFIG, records, previous, STAMP)
        self.assertEqual(current["publications"]["test"]["citations"], 0)

    def test_missing_and_ambiguous_records_never_become_zero(self):
        config = copy.deepcopy(CONFIG)
        config["publications"] += [{"id": "missing", "title": "Missing Paper"}, {"id": "duplicate", "title": "Same Title"}]
        records, _ = parse_profile(page(row(), row("Same Title", key="two"), row("Same Title", key="three")), PROFILE)
        result = build_snapshot(config, records, {}, STAMP)
        self.assertIsNone(result["publications"]["missing"]["citations"])
        self.assertIsNone(result["publications"]["duplicate"]["citations"])

    def test_last_confirmed_count_is_retained(self):
        records, _ = parse_profile(page(row(), row("Old Paper", count="9", key="two")), PROFILE)
        config = copy.deepcopy(CONFIG)
        config["publications"].append({"id": "old", "title": "Old Paper"})
        previous = build_snapshot(config, records, {}, STAMP)
        current = build_snapshot(config, records[:1], previous, "2026-10-30T01:00:00Z")
        old = current["publications"]["old"]
        self.assertEqual((old["citations"], old["checked_at"], old["status"]), (9, STAMP, "stale"))

    def test_explicit_alias_and_normalized_titles(self):
        config = copy.deepcopy(CONFIG)
        config["publications"][0].pop("scholar_id")
        config["publications"][0]["aliases"] = ["Other: paper"]
        records, _ = parse_profile(page(row("OTHER — Paper")), PROFILE)
        self.assertEqual(build_snapshot(config, records, {}, STAMP)["publications"]["test"]["citations"], 12)

    def test_failed_sync_leaves_both_files_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "config.json").write_text(json.dumps(CONFIG))
            (base / "blocked.html").write_text("<html>Unusual traffic</html>")
            (base / "scholar-citations.json").write_text(json.dumps({"profile_id": PROFILE}))
            (base / "scholar-citations.js").write_text("previous snapshot")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_citations.py"), "--config", str(base / "config.json"), "--html", str(base / "blocked.html"), "--output-dir", str(base)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((base / "scholar-citations.js").read_text(), "previous snapshot")
            self.assertEqual(json.loads((base / "scholar-citations.json").read_text()), {"profile_id": PROFILE})


class SiteIntegrationTests(unittest.TestCase):
    def test_every_publication_has_one_mapping_and_badge(self):
        doc = Document((ROOT / "index.html").read_text())
        config = json.loads((ROOT / "scripts/scholar-publications.json").read_text())
        papers = config["publications"]
        self.assertEqual({normalize(p["title"]) for p in papers}, {normalize(n.text()) for n in doc.root.find_all("papertitle")})
        links = doc.root.find_all("citation-count")
        self.assertEqual(len(links), len(papers))
        self.assertEqual({p["id"] for p in papers}, {n.attrs["data-citation-id"] for n in links})

    def test_bundled_snapshots_agree(self):
        snapshot = json.loads((ROOT / "data/scholar-citations.json").read_text())
        javascript = (ROOT / "data/scholar-citations.js").read_text()
        embedded = javascript.split("window.SCHOLAR_CITATIONS = ", 1)[1].rstrip().removesuffix(";")
        self.assertEqual(json.loads(embedded), snapshot)


if __name__ == "__main__":
    unittest.main()
