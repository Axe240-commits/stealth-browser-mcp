"""X/Twitter-specific search extraction helpers."""

from __future__ import annotations

from urllib.parse import quote_plus

VALID_X_SEARCH_MODES = {"top", "latest"}


def _js_extract_tweets_script() -> str:
    return r"""
        (maxItems) => {
            const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
            const parseCount = (value) => {
                const raw = clean(value).toLowerCase();
                if (!raw) return null;
                const m = raw.match(/^([0-9]*\.?[0-9]+)\s*([kmb])?$/i);
                if (!m) return raw;
                const n = parseFloat(m[1]);
                const suffix = m[2];
                if (!suffix) return Math.round(n);
                const mult = suffix === 'k' ? 1_000 : suffix === 'm' ? 1_000_000 : 1_000_000_000;
                return Math.round(n * mult);
            };

            const tweets = [];
            const seen = new Set();
            const cards = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));

            for (const card of cards) {
                if (tweets.length >= maxItems) break;

                const textNode = card.querySelector('[data-testid="tweetText"]');
                const text = clean(textNode ? textNode.innerText : card.innerText);
                if (!text) continue;

                const links = Array.from(card.querySelectorAll('a[href]'));
                const statusLink = links.find(a => /\/status\//.test(a.getAttribute('href') || ''));
                const tweetUrl = statusLink ? statusLink.href : null;
                if (tweetUrl && seen.has(tweetUrl)) continue;
                if (tweetUrl) seen.add(tweetUrl);

                const timeEl = card.querySelector('time');
                const timestamp = timeEl ? timeEl.getAttribute('datetime') : null;

                const userLinks = links.filter(a => {
                    const href = a.getAttribute('href') || '';
                    return /^\/[A-Za-z0-9_]{1,20}$/.test(href);
                });
                const username = userLinks.length ? (userLinks[0].getAttribute('href') || '').replace(/^\//, '') : null;
                const authorName = userLinks.length ? clean(userLinks[0].textContent) || username : username;

                const stats = {};
                for (const name of ['reply', 'retweet', 'like', 'bookmark', 'view']) {
                    const el = card.querySelector(`[data-testid="${name}"]`);
                    if (!el) continue;
                    const textValue = clean(el.innerText || el.textContent || '');
                    if (!textValue) continue;
                    const firstLine = textValue.split(' ')[0];
                    stats[`${name}_count`] = parseCount(firstLine);
                }

                const promoted = /promoted/i.test(clean(card.innerText));
                const hasMedia = Boolean(card.querySelector('[data-testid="tweetPhoto"], video, [aria-label*="Image"], [aria-label*="Video"]'));

                tweets.push({
                    author_name: authorName,
                    username,
                    tweet_text: text,
                    timestamp,
                    tweet_url: tweetUrl,
                    has_media: hasMedia,
                    is_promoted: promoted,
                    ...stats,
                });
            }

            return {
                tweets,
                extracted_count: tweets.length,
                page_url: window.location.href,
                page_title: document.title,
            };
        }
    """


def build_x_search_url(query: str, mode: str = "top") -> str:
    mode = mode.lower().strip()
    if mode not in VALID_X_SEARCH_MODES:
        raise ValueError(f"Invalid mode: {mode!r}. Valid: {sorted(VALID_X_SEARCH_MODES)}")

    encoded = quote_plus(query)
    base = f"https://x.com/search?q={encoded}&src=typed_query"
    if mode == "latest":
        return f"{base}&f=live"
    return base


async def extract_x_search_results(page, max_items: int = 20) -> dict:
    """Extract structured tweet cards from an X search result page."""
    max_items = max(1, min(int(max_items), 50))

    data = await page.evaluate(_js_extract_tweets_script(), max_items)
    data["max_items"] = max_items
    return data


async def read_x_thread(page, max_items: int = 20) -> dict:
    """Extract the visible tweets from a thread / tweet detail page."""
    max_items = max(1, min(int(max_items), 50))
    data = await page.evaluate(_js_extract_tweets_script(), max_items)
    tweets = data.get("tweets", [])
    main_tweet = tweets[0] if tweets else None
    replies = tweets[1:] if len(tweets) > 1 else []
    return {
        **data,
        "main_tweet": main_tweet,
        "replies": replies,
        "reply_count_extracted": len(replies),
        "max_items": max_items,
    }
