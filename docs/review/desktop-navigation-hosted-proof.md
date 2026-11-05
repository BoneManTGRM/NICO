# Hosted desktop navigation proof

The existing PR WebKit proof now includes eight synthetic desktop cases: English
and es-MX, each with reset, invalid identity, Comprehensive switch and Express
switch. The original twenty reviewer-assistance cases remain required.

The new cases load the actual built assessment pages at 1280x1000, wait for the
application hydration marker, and traverse the real navigation with Tab,
Shift+Tab and Enter. They require the current-page marker, native focus-visible
state and changed focus styles, keyboard opening of More, locale-preserving links,
and removal/replacement of stale run/customer/project/edition scope. Primary,
brand and language hrefs are checked before and after the URL transition. Final
Review is activated with Enter and its observed navigation URL is checked exactly.

Reset and run switch are simulated through native history.replaceState; this is
not a test of the application's reset button or assessment creation. Primary and
language links are checked for destination hrefs, not Enter-activated. Final Review
navigation receives a fixed synthetic HTML response; this proves the destination
request, not the real final-review page, authorization, or backend behavior.

The normal hosted WebKit launch, existing process network guard, 180-second proof
budget, four-minute workflow step and aggregate 20MiB artifact cap are unchanged.
The navigation contexts add only exact loopback GET document paths for the two
assessment pages and the synthetic destination. They block every other API request
and all writes. The original reviewer context's request policy is unchanged.
Two fixed-name desktop screenshots are added to the existing artifact allowlist.
Overall completion requires successful return and both complete unique passed-case
matrices, including failures after all cases have been recorded.

Offline oracle/isolation/staging tests and independent review do not establish
browser success. The existing PR job must execute this coverage on the final head.
Do not retry a denied local browser launch or change its sandbox. No rendered
success is claimed until that hosted job passes.

Automated DOM, focus and keyboard observations are not screen-reader speech
observations. The manifest keeps screen_reader_observed=false. Actual assistive
technology announcements, evidence-panel scrolling and sampling-control behavior
remain outside these navigation cases.
