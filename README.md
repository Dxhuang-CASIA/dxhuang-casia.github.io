This personal academic website is based on [Jon Barron's template](https://jonbarron.info/).

## Google Scholar citation counts

Each publication shows a linked `Citation: N` count from the public Scholar profile `01Pcm-AAAAAJ`. The initial snapshot is bundled with the site, including local `file://` previews. On page load, `scripts/citations.js` also fetches the latest JSON from this repository's `main` branch. Link tooltips show when the data was checked.

Use a local Codex scheduled task on the owner's Mac daily at **07:17 Asia/Hong_Kong**. The Mac must be awake, connected to the internet, and running Codex. Google Scholar returned HTTP 403 on GitHub-hosted runners, so `.github/workflows/scholar-citations.yml` only validates the data and code; it does not fetch Scholar. No third-party API key or paid citation service is needed.

`scripts/sync_citations_to_github.py` makes a temporary clone of the latest remote `main`, fetches Scholar, and commits and pushes only `data/scholar-citations.json` and `data/scholar-citations.js`. It uses this checkout's Git author identity and existing GitHub authentication. Staged or unfinished edits in this checkout are left untouched. The browser reads the latest JSON on page load, and the normal GitHub Pages publishing settings remain in place. The script never force-pushes; a concurrent remote update or authentication failure stops publishing.

Scholar can also restrict requests from a Mac. HTTP errors, challenges, incomplete responses, or a complete matching failure stop the sync and leave published data intact; the script does not bypass CAPTCHAs or rotate proxies. If an individual article disappears, its last verified count and date are retained. An unknown count is never displayed as zero.

Because daily updates are pushed from a temporary clone, this checkout may fall behind `origin/main`. Before pushing later homepage edits, commit those edits and run `git pull --rebase origin main`, then `git push origin main`. Resolve any reported conflicts before pushing.

### Adding or updating a publication

1. Add the publication to `index.html` and give its citation link a unique `data-citation-id`.
2. Add the same ID, title, and (when available) `scholar_id` to `scripts/scholar-publications.json`. Explicit `aliases` support verified alternate titles. Matching uses the Scholar article ID first, then unique normalized exact titles; it does not guess with fuzzy matching.
3. Commit and push the publication changes, then run the local publisher. Update the hardcoded repository URL in `scripts/citations.js` if using a fork or a different default branch.

Local commands (Python 3.9+; no external Python packages required):

```sh
# Fetch and publish citation data from the latest remote main:
python3 scripts/sync_citations_to_github.py
# Run offline checks:
python3 -m unittest discover -s tests -p 'test_citation*.py' -v
node --test tests/citations.test.cjs
```

The publisher uses the system CA bundle `/etc/ssl/cert.pem` on macOS if Python has no default bundle. HTTPS certificate verification stays enabled. To fetch into this checkout without committing or pushing, run `SSL_CERT_FILE=/etc/ssl/cert.pem python3 scripts/sync_citations.py` on macOS.

For unattended SSH pushes on macOS, unlock the existing GitHub key once in Terminal with `ssh-add --apple-use-keychain ~/.ssh/id_rsa` and enter its passphrase there. The publisher uses macOS Keychain and never requests a passphrase interactively. Test the publisher manually when setting up the task. If Scholar returns HTTP 403, keep the previous data and wait until the next scheduled day instead of repeatedly retrying.

For offline verification, use `python3 scripts/sync_citations.py --html /path/to/saved-complete-scholar-profile.html`. This requires a complete profile page; a paginated partial response is rejected.
