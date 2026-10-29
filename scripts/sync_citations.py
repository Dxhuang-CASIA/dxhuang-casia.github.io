#!/usr/bin/env python3
"""Sync this site's publications from its public Google Scholar profile.

Only the Python standard library is needed. A blocked or malformed response
fails the run before either published data file is replaced.
"""

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VOID_TAGS = set("area base br col embed hr img input link meta param source track wbr".split())


class Element:
    def __init__(self, tag, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def text(self):
        # Scholar represents mathematical superscripts as accessible SVGs.
        if self.tag == "svg":
            return self.attrs.get("aria-label", "")
        return "".join(c.text() if isinstance(c, Element) else c for c in self.children)

    def find_all(self, class_name):
        found = [self] if class_name in self.attrs.get("class", "").split() else []
        for child in self.children:
            if isinstance(child, Element):
                found.extend(child.find_all(class_name))
        return found


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]
        self.by_id = {}
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if "id" in node.attrs:
            self.by_id[node.attrs["id"]] = node
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def normalize(title):
    return "".join(c for c in unicodedata.normalize("NFKD", title).casefold() if c.isalnum())


def article_url(scholar_id):
    return "https://scholar.google.com/citations?" + urlencode({
        "view_op": "view_citation", "hl": "en", "citation_for_view": scholar_id,
        "user": scholar_id.split(":", 1)[0],
    })


def safe_scholar_url(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc == "scholar.google.com"


def parse_profile(html, profile_id):
    doc = Document(html)
    records = []
    for row in doc.root.find_all("gsc_a_tr"):
        titles = row.find_all("gsc_a_at")
        counts = row.find_all("gsc_a_ac")
        if len(titles) != 1 or len(counts) != 1:
            raise ValueError("Incomplete Scholar article row; keeping the previous data.")
        scholar_id = parse_qs(urlparse(titles[0].attrs.get("href", "")).query).get("citation_for_view", [""])[0]
        if not scholar_id.startswith(profile_id + ":") or not scholar_id.split(":", 1)[1]:
            raise ValueError("Unexpected Scholar profile or missing article ID.")
        count_text = counts[0].text().strip().rstrip("*").strip().replace(",", "")
        # A verified article row with an empty citation anchor is Scholar's zero.
        if count_text and not re.fullmatch(r"[0-9]+", count_text):
            raise ValueError("Unrecognized citation count: " + count_text)
        href = counts[0].attrs.get("href") or article_url(scholar_id)
        href = urljoin("https://scholar.google.com", href)
        if not safe_scholar_url(href):
            raise ValueError("Unexpected citation destination.")
        records.append({
            "scholar_id": scholar_id,
            "title": " ".join(titles[0].text().split()),
            "citations": int(count_text or "0"),
            "citation_url": href,
        })
    if not records:
        raise ValueError("No Scholar article rows found (possibly a block or CAPTCHA); keeping the previous data.")
    next_button = doc.by_id.get("gsc_bpf_next")
    has_more = next_button is not None and "disabled" not in next_button.attrs
    return records, has_more


def fetch_profile(profile_id):
    records = []
    for start in range(0, 500, 100):
        url = "https://scholar.google.com/citations?" + urlencode({
            "user": profile_id, "hl": "en", "pagesize": 100, "cstart": start,
        })
        request = Request(url, headers={"User-Agent": "ScholarCitationSync/1.0 (+https://dxhuang-casia.github.io/)"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
        page, has_more = parse_profile(html, profile_id)
        records.extend(page)
        if not has_more:
            return records
    raise ValueError("Profile exceeded the pagination limit; keeping the previous data.")


def build_snapshot(config, records, previous, checked_at):
    if previous and previous.get("profile_id") != config["profile_id"]:
        raise ValueError("Cached data belongs to a different Scholar profile.")
    by_id = {}
    by_title = {}
    for record in records:
        if record["scholar_id"] in by_id:
            raise ValueError("Duplicate Scholar article IDs; refusing a partial update.")
        by_id[record["scholar_id"]] = record
        by_title.setdefault(normalize(record["title"]), []).append(record)
    publications = {}
    matched = 0
    for paper in config["publications"]:
        if paper["id"] in publications:
            raise ValueError("Duplicate site publication ID: " + paper["id"])
        record = by_id.get(paper.get("scholar_id"))
        if record is None:
            candidates = {}
            for title in [paper["title"]] + paper.get("aliases", []):
                for candidate in by_title.get(normalize(title), []):
                    candidates[candidate["scholar_id"]] = candidate
            # Never choose an approximate match or silently pick a duplicate title.
            if len(candidates) == 1:
                record = next(iter(candidates.values()))
        if record:
            matched += 1
            publications[paper["id"]] = dict(record, title=paper["title"], status="ok", checked_at=checked_at)
        else:
            old = previous.get("publications", {}).get(paper["id"], {})
            if type(old.get("citations")) is int and old["citations"] >= 0:
                publications[paper["id"]] = dict(old, status="stale")
            else:
                publications[paper["id"]] = {
                    "title": paper["title"], "citations": None, "checked_at": None,
                    "citation_url": "https://scholar.google.com/scholar?" + urlencode({"q": '"' + paper["title"] + '"'}),
                    "status": "unavailable",
                }
            print("No unambiguous Scholar record: " + paper["title"], file=sys.stderr)
    if not matched:
        raise ValueError("No site publications matched; keeping the previous data.")
    return {
        "schema_version": 1, "source": "Google Scholar", "profile_id": config["profile_id"],
        "profile_url": "https://scholar.google.com/citations?user=" + config["profile_id"],
        "updated_at": checked_at, "publications": publications,
    }


def write_snapshot(snapshot, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    # The JS snapshot also works in the user's file:// preview, without fetch.
    files = {
        "scholar-citations.json": encoded,
        "scholar-citations.js": "// Generated by scripts/sync_citations.py.\nwindow.SCHOLAR_CITATIONS = " + encoded.rstrip() + ";\n",
    }
    for name, content in files.items():
        temporary = output_dir / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(output_dir / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scripts/scholar-publications.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--html", type=Path, help="Read a previously downloaded complete Scholar profile for offline verification.")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    previous_path = args.output_dir / "scholar-citations.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    if args.html:
        records, has_more = parse_profile(args.html.read_text(encoding="utf-8"), config["profile_id"])
        if has_more:
            raise ValueError("Offline input is incomplete; download all profile pages first.")
    else:
        records = fetch_profile(config["profile_id"])
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    snapshot = build_snapshot(config, records, previous, checked_at)
    write_snapshot(snapshot, args.output_dir)
    matched = sum(p["status"] == "ok" for p in snapshot["publications"].values())
    print("Updated {}/{} publications from Google Scholar.".format(matched, len(snapshot["publications"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Citation sync failed: " + str(error), file=sys.stderr)
        sys.exit(1)
