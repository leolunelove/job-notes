# Job sources

Job Notes refreshes 7 public job feeds and 36 selected employer boards. The employer inventory is in `dist/sources.json`; this is selected coverage, not access to every employer on those platforms.

- Remotive: public JSON, every 6 hours; listings may be delayed 24 hours.
- Arbeitnow: public JSON, up to 8 pages, every 6 hours.
- Himalayas: public JSON, up to 5 pages, daily.
- We Work Remotely: public RSS, every 6 hours; attribution and listing links retained.
- Startup Jobs: public RSS, latest 50 jobs, every 6 hours; attribution and listing links retained.
- Remote OK: public JSON, recent-job window, every 6 hours; attribution and listing links retained.
- Jobicy: public JSON, up to 5 pages of 200 jobs, every 6 hours; attribution and listing links retained.
- Greenhouse: 23 employer boards, every 6 hours.
- Ashby: 8 employer boards, every 6 hours.
- Lever: 5 employer boards, every 6 hours, paginated in pages of 100 (hard cap 5,000 per employer).

All requests are bounded and server-side. No CV or user preference is sent to a job provider. GitHub Actions refreshes the feed while the app is closed. Individual failures retain recent cached results marked unverified; results unconfirmed for 48 hours are omitted. Only a successful complete refresh can count an absent listing toward closure, which requires two such refreshes. Rolling feeds never close a listing by absence. Explicit recognised past deadlines are hidden.

Deduplication prefers the current employer board and retains all observed source attribution links. It uses canonical URLs or exact normalised company/title/location, and does not merge fuzzy titles or different locations. This can still combine distinct requisitions with identical titles and locations; it is a shortlist rather than a requisition database.

The static search feed retains exact full-description matches for the built-in skill vocabulary. Custom skill terms use an on-demand word index: multiple words must all appear, and this does not establish phrase order. Full description buckets load when opening a job; original listings remain accessible if that request fails. A compact excerpt is available immediately. Content-addressed URLs prevent mixing cached details from different builds.

## Not connected

- X/Twitter: automated search needs an approved developer app and bearer credentials, with applicable usage charges. No scraping fallback or credentials are shipped in the public app. It must not be presented as connected without provisioning and an end-to-end check. Prefer identifying hiring posts with direct employer links, resolving actual job information, and keeping social leads explicitly separate from verified job listings.
- Wellfound (formerly AngelList Talent): no supported public listings feed was connected. The app provides a direct browse link; it does not claim to import their jobs.
- Y Combinator: browse link only, not an imported source.

## References

- https://weworkremotely.com/remote-job-rss-feed
- https://startup.jobs/api/
- https://remoteok.com/api
- https://github.com/Jobicy/remote-jobs-api
- https://docs.greenhouse.io/job-board.html
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://github.com/lever/postings-api
- https://docs.x.com/x-api/posts/search/introduction
