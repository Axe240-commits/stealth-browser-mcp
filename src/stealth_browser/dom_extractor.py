"""Structured DOM data extraction via page.evaluate()."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Page

ALLOWED_SECTIONS = frozenset(
    {"metadata", "og_tags", "json_ld", "headings", "links", "tables", "forms"}
)

_JS_EXTRACT = """
() => {
    const result = {};

    // --- metadata ---
    const getMeta = (name) => {
        const el = document.querySelector(
            `meta[name="${name}"], meta[property="${name}"]`
        );
        return el ? el.getAttribute("content") || "" : "";
    };
    result.metadata = {
        description: getMeta("description"),
        canonical: (() => {
            const el = document.querySelector('link[rel="canonical"]');
            return el ? el.getAttribute("href") || "" : "";
        })(),
        language: document.documentElement.lang || "",
        author: getMeta("author"),
    };

    // --- og_tags ---
    const ogTags = {};
    document.querySelectorAll('meta[property^="og:"]').forEach((el) => {
        const prop = el.getAttribute("property");
        if (prop) ogTags[prop] = (el.getAttribute("content") || "").slice(0, 500);
    });
    result.og_tags = ogTags;

    // --- json_ld (max 10, try/catch per script) ---
    const jsonLd = [];
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (let i = 0; i < Math.min(scripts.length, 10); i++) {
        try {
            const text = scripts[i].textContent || "";
            if (text.trim()) {
                const parsed = JSON.parse(text);
                jsonLd.push(parsed);
            }
        } catch (e) {
            // skip malformed json-ld
        }
    }
    result.json_ld = jsonLd;

    // --- headings ---
    const headings = [];
    document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((el) => {
        if (headings.length < 200) {
            const text = (el.textContent || "").trim().slice(0, 300);
            if (text) {
                headings.push({
                    level: parseInt(el.tagName[1]),
                    text: text,
                });
            }
        }
    });
    result.headings = headings;

    // --- links (deduplicated by href, max 500, text capped at 200) ---
    const seenHrefs = new Set();
    const links = [];
    document.querySelectorAll("a[href]").forEach((el) => {
        if (links.length >= 500) return;
        const href = el.href; // absolute resolved by browser
        if (!href || seenHrefs.has(href)) return;
        seenHrefs.add(href);
        links.push({
            text: (el.textContent || "").trim().slice(0, 200),
            href: href,
        });
    });
    result.links = links;

    // --- tables (max 50 tables, 100 rows each, 500 chars per cell) ---
    const tables = [];
    document.querySelectorAll("table").forEach((table) => {
        if (tables.length >= 50) return;
        const rows = [];
        table.querySelectorAll("tr").forEach((tr) => {
            if (rows.length >= 100) return;
            const cells = [];
            tr.querySelectorAll("td, th").forEach((cell) => {
                cells.push((cell.textContent || "").trim().slice(0, 500));
            });
            if (cells.length > 0) rows.push(cells);
        });
        if (rows.length > 0) tables.push(rows);
    });
    result.tables = tables;

    // --- forms (max 20 forms) ---
    const forms = [];
    document.querySelectorAll("form").forEach((form) => {
        if (forms.length >= 20) return;
        const fields = [];
        form.querySelectorAll("input, select, textarea, button").forEach((el) => {
            if (fields.length >= 50) return;
            fields.push({
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute("type") || "",
                name: el.getAttribute("name") || "",
                id: el.getAttribute("id") || "",
            });
        });
        forms.push({
            action: form.getAttribute("action") || "",
            method: (form.getAttribute("method") || "GET").toUpperCase(),
            fields: fields,
        });
    });
    result.forms = forms;

    return result;
}
"""


async def extract_dom_data(
    page: Page, include: list[str] | None = None
) -> dict:
    """Extract structured data from the DOM.

    Args:
        page: Patchright page instance.
        include: Sections to include. None = all sections.
            Allowed: metadata, og_tags, json_ld, headings, links, tables, forms.

    Returns:
        Dict with requested sections.

    Raises:
        ValueError: If include contains unknown section names.
    """
    if include is not None:
        unknown = set(include) - ALLOWED_SECTIONS
        if unknown:
            raise ValueError(
                f"Unknown sections: {sorted(unknown)}. "
                f"Allowed: {sorted(ALLOWED_SECTIONS)}"
            )

    raw = await page.evaluate(_JS_EXTRACT)

    if include is not None:
        return {k: v for k, v in raw.items() if k in include}

    return raw
