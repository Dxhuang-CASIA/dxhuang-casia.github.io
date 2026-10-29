This personal academic website is based on [Jon Barron's template](https://jonbarron.info/).

## Google Scholar citation counts

Each publication shows a linked `Citation: N` count from the public Scholar profile `01Pcm-AAAAAJ`. The initial snapshot is bundled with the site, including local `file://` previews. On page load, `scripts/citations.js` also fetches the latest JSON from this repository's `main` branch. Link tooltips show when the data was checked.

`.github/workflows/scholar-citations.yml` updates the counts daily at approximately **07:17 Asia/Hong_Kong** (23:17 UTC; GitHub can delay scheduled runs). It can also be run through **Actions → Update Google Scholar citations → Run workflow**. After pushing these changes to `main`, ensure Actions is enabled and the workflow is allowed to write repository contents. No API key or paid service is used.

The job commits only `data/scholar-citations.json` and `data/scholar-citations.js`. The browser reads the latest JSON directly because [commits made using `GITHUB_TOKEN` do not trigger a GitHub Pages build](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). Existing Pages publishing settings can remain in place. Branch protection rules that prohibit bot pushes must be handled in the repository settings; the workflow does not override them.

Scholar can restrict automated requests. HTTP errors, challenges, incomplete responses, or a complete matching failure fail the workflow and leave published data intact; the script does not bypass CAPTCHAs or rotate proxies. If an individual article disappears, its last verified count and date are retained. An unknown count is never displayed as zero. Public repositories' scheduled workflows may be disabled by GitHub after 60 days without repository activity; re-enable the workflow in Actions if needed.

### Adding or updating a publication

1. Add the publication to `index.html` and give its citation link a unique `data-citation-id`.
2. Add the same ID, title, and (when available) `scholar_id` to `scripts/scholar-publications.json`. Explicit `aliases` support verified alternate titles. Matching uses the Scholar article ID first, then unique normalized exact titles; it does not guess with fuzzy matching.
3. Run the sync or trigger the workflow. Update the hardcoded repository URL in `scripts/citations.js` if using a fork or a different default branch.

Local commands (Python 3.9+; no external Python packages required):

```sh
python3 scripts/sync_citations.py
python3 -m unittest discover -s tests -p 'test_citations.py' -v
node --test tests/citations.test.cjs
```

If a macOS Python installation reports a missing CA certificate bundle, use its certificate installer or run `SSL_CERT_FILE=/etc/ssl/cert.pem python3 scripts/sync_citations.py` to use the system CA bundle. Keep HTTPS certificate verification enabled.

For offline verification, use `python3 scripts/sync_citations.py --html /path/to/saved-complete-scholar-profile.html`. This requires a complete profile page; a paginated partial response is rejected.
