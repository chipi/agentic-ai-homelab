/**
 * Make external links open in a new tab/window.
 *
 * Hooks into Material for MkDocs' `document$` observable so this runs on
 * the initial page load AND on every instant-navigation swap (the site
 * uses navigation.instant per mkdocs.yml).
 *
 * Security: adds rel="noopener noreferrer" alongside target="_blank" so
 * the opened tab can't access window.opener and the source URL is not
 * leaked via the Referer header.
 *
 * Links are classified as external when their href starts with http:// or
 * https:// AND is not same-origin. Relative paths (../page.md),
 * anchor-only fragments (#section), mailto:, tel:, etc. are left alone.
 */
document$.subscribe(function () {
  const internalOrigin = window.location.origin;

  document.querySelectorAll("a[href]").forEach(function (link) {
    const href = link.getAttribute("href");
    if (!href) return;

    const isAbsolute = href.startsWith("http://") || href.startsWith("https://");
    if (!isAbsolute) return;
    if (href.startsWith(internalOrigin)) return;

    link.setAttribute("target", "_blank");

    const rel = link.getAttribute("rel") || "";
    if (!/\bnoopener\b/.test(rel)) {
      link.setAttribute("rel", (rel + " noopener noreferrer").trim());
    }
  });
});
