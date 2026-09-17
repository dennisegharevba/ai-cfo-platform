# A real gap: Telegram send failures hid their actual cause

## How this was found

Live testing of Chief Execution Officer's real Telegram send hit a
genuine `400 Bad Request`:

```
send_error: Telegram sendMessage request failed: 400 Client Error:
Bad Request for url: https://api.telegram.org/bot.../sendMessage
```

This is genuinely ambiguous. A 400 from Telegram's `sendMessage`
endpoint could mean the `chat_id` doesn't correspond to a real
conversation, or it could mean the message TEXT itself has a formatting
problem Telegram's Markdown parser can't handle — two completely
different problems requiring completely different fixes, and the error
message gave no way to tell them apart.

## Root cause

`telegram/telegram_alerter.py` called `resp.raise_for_status()`
immediately after the request:

```python
resp = requests.post(url, json=payload, timeout=self.timeout)
resp.raise_for_status()   # <- raises immediately on any 4xx/5xx
data = resp.json()        # <- never reached on an HTTP error
```

Telegram's Bot API returns a real JSON body with a `description` field
explaining exactly what went wrong — even on 4xx/5xx status codes (e.g.
`"Bad Request: chat not found"` vs.
`"Bad Request: can't parse entities: Character '-' is reserved and must
be escaped"`). `raise_for_status()` raises before that body is ever read,
throwing away the one piece of information that would have made the
failure diagnosable.

## The fix

The response body is now read (when parseable) BEFORE checking whether
the HTTP status was an error, so Telegram's own `description` is
available regardless of which kind of failure occurred:

```python
try:
    data = resp.json()
except ValueError:
    data = None

if not resp.ok:
    if data and "description" in data:
        raise TelegramError(f"Telegram API rejected the message: {data['description']}")
    raise TelegramError(f"Telegram sendMessage request failed: {resp.status_code} {resp.reason} for url: {resp.url}")
```

If Telegram (or something in front of it) returns an HTTP error with no
parseable JSON at all, the fallback still gives a clear status-line
error rather than crashing on a `None` body.

## Testing

3 new tests: a 400 with a `"chat not found"` description surfaces that
exact text; a 400 with a Markdown-parsing description surfaces that
exact text (proving the fix genuinely distinguishes the two realistic
causes, not just one); and an HTTP error with no JSON body at all still
produces a clear, non-crashing error. All 4 existing tests updated to
properly set `resp.ok` (needed since the fix now checks that directly
rather than relying on `raise_for_status()`) and still pass unchanged.
**615 tests total.**

## Next step

This fix doesn't resolve the original send failure — it makes the ACTUAL
reason visible so it can be diagnosed. Re-running
`python scripts/demo_execution_officer.py --send-real` after this fix
will show which of the two real causes it actually was.
