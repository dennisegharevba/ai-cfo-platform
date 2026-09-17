# News feed default changed — the old one wasn't market news

## How this was found

A live run of Chief Sentiment Officer returned an exact `0.0` score.
Unlike the `±100.0` clamping issues found earlier in this session, an
exact `0.0` from a small keyword-based scorer isn't automatically
suspicious on its own — it could honestly mean "no strong bullish/bearish
language today." Rather than assume either way, the actual 10 fetched
headlines were inspected directly.

Every single one was a MarketWatch personal-finance advice column:

```
'My wife and I are both retired': Do we dip into our $2.3 million fund
to pay off our $300,000 mortgage at 2.9%?

'I don't wish to be cold-hearted': My elderly relative can no longer
care for himself. Am I wrong to leave his care to the state?

Social Security's funding crisis is the elephant in the room. But
don't ignore the mouse.
```

Zero of ten had anything to do with markets or the economy. This wasn't
a keyword-coverage gap — no reasonable sentiment lexicon should find
bullish/bearish market signal in a reader's mortgage-payoff question.
The feed itself, `http://feeds.marketwatch.com/marketwatch/topstories/`
(configured as the platform's default), was returning the wrong kind of
content despite being labeled "top stories."

## Investigation, not assumption

`scripts/debug_news_feeds.py` was built to test the current default
against several candidate alternatives side by side, showing real
headlines and real keyword-match results for each — rather than guess at
a replacement URL. The user ran it live, twice confirming the original
feed's problem (0 of 10 relevant on a completely independent pull) and
finding a genuinely working alternative:

**MarketWatch MarketPulse** (`http://feeds.marketwatch.com/marketwatch/marketpulse/`)
returned real, current, market-moving headlines:

```
Jobless claims fall to lowest level since mid-May
Consumer credit growth soars in December          [BULLISH: 'soar']
U.S. productivity slows down in fourth quarter while unit labor costs accelerate
U.S. stock futures and bond yields drop on reports Putin has updated nuclear doctrine
Amazon says it had best-ever Thanksgiving Holiday week with record sales
```

Genuine economic data releases, genuine corporate news, and one real
keyword match — exactly what this department needs to work with.

Two other candidates (CNBC, Yahoo Finance) were tried but failed for
unrelated reasons (a 403 and a 429 respectively) — neither confirmed
working, so neither was adopted. Only the one actually verified live was
changed.

## The fix

`config/settings.py`'s `NEWS_RSS_URL` default changed from the
"topstories" feed to the confirmed-working, confirmed-relevant
"marketpulse" feed. `docs/CONFIGURATION.md`'s description updated to
match. No test hardcoded the old URL, so no test changes were needed —
607 tests, all passing, unaffected.

## Honest scope

This fixes the DEFAULT. If `NEWS_RSS_URL` is already set in a `.env`
file to something else, this change has no effect — the environment
variable always wins over the code default, exactly as intended.
