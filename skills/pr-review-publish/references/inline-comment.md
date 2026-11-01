# Inline Comment Body

The body of each per-finding inline review comment. Anchored to a specific `file:line` (or line range) in the PR diff. GitHub renders it under the diff hunk with a severity badge and optional "Commit suggestion" button.

## Body shape

````markdown
![<severity>](https://img.shields.io/badge/Priority-<Label>-<color>)

<one or two short paragraphs: what's wrong, why it matters>

```suggestion
<exact replacement for the anchored line range>
```
````

The `suggestion` fenced block is OPTIONAL — include only when you can produce an exact, drop-in replacement for the line(s) this comment anchors to.

## Severity badge URLs

| Severity | URL |
|----------|-----|
| Critical | `https://img.shields.io/badge/Priority-Critical-red` |
| Important | `https://img.shields.io/badge/Priority-Important-orange` |
| Suggestion | `https://img.shields.io/badge/Priority-Suggestion-blue` |

Render in the body as `![<short-label>](<url>)`. Examples:
- `![critical](https://img.shields.io/badge/Priority-Critical-red)`
- `![important](https://img.shields.io/badge/Priority-Important-orange)`
- `![suggestion](https://img.shields.io/badge/Priority-Suggestion-blue)`

Alt text matters for screen readers and for the case where shields.io is briefly down — keep it short and accurate.

## `suggestion` block — when and how

GitHub recognises a fenced code block tagged `suggestion`. Its content REPLACES the anchored line range when the reviewer clicks "Commit suggestion".

Rules:
- **Single-line comment** → suggestion replaces THAT line.
- **Multi-line comment** (`start_line` + `line`) → suggestion replaces the inclusive range.
- **No leading-whitespace stripping.** Whatever indentation you write is what gets committed.
- **No partial-line edits.** GitHub replaces whole lines, not substrings.
- **Don't include the leading `+` or `-` markers.** Just write the resulting code.
- **Omit the block** when:
  - The fix involves changes outside the anchored range
  - The fix needs multiple non-contiguous edits
  - You're not certain the exact replacement is correct

## Worked examples

### Single-line, with suggestion

Anchored to `Packages/swift-core-logger/Sources/SCLogger/Logging.swift:39`:

````markdown
![important](https://img.shields.io/badge/Priority-Important-orange)

The documentation comment states that `isNetworkLoggingEnabled` defaults to `true`, but the implementation on line 43 initializes it to `false`. Based on the PR description and `docs/logging.md`, `false` is the intended default. Update the comment to match the implementation.

```suggestion
  /// Defaults to `false`. Flip from anywhere at runtime:
```
````

### Multi-line, with suggestion

Anchored to `BinoEventMonitor.swift:29–32` (start_line=29, line=32):

````markdown
![important](https://img.shields.io/badge/Priority-Important-orange)

`cURLDescription`'s no-arg overload runs on Alamofire's `underlyingQueue`, not main — but routing through our dedicated `bino.api.eventmonitor` queue is cleaner separation. More importantly, the closure fires async, so the toggle could flip between the outer guard at line 24 and the closure executing — add an inner guard.

```suggestion
    request.cURLDescription(on: queue) { [weak self] curl in
      guard Logger.isNetworkLoggingEnabled else { return }
      self?.emit(SensitiveDataRedactor.redactCurl(curl), level: .debug)
    }
```
````

### No suggestion (fix spans multiple files)

Anchored to `apps/bino-app/src/pages/Notifications.tsx:46`:

````markdown
![critical](https://img.shields.io/badge/Priority-Critical-red)

`handleAccept` / `handleDecline` only `console.log` then `toast.success(...)`. No API call, so the friend request reappears on refresh while the user sees a lying success toast.

Fix: wire to the real mutation (`useAcceptFriendRequest` in `features/friends/api/`), OR remove the buttons until the endpoint exists. Cannot inline a suggestion because the fix imports a hook from another file.
````

## Anti-patterns

- **Suggestion that doesn't apply cleanly.** GitHub shows "This suggestion cannot be applied" — looks unprofessional. Test mentally: would copying this block exactly into the file produce the right result?
- **Multi-paragraph essays per finding.** 1–2 short paragraphs. If you need more, link to a report file instead.
- **Severity inflation.** Don't mark every finding "Critical". See `severity-rubric.md`.
- **Repeating what the diff already shows.** "On line 39, `defaults to true` is wrong" — don't restate the line. Lead with the WHY.
- **Embedding secrets / PII from the code being reviewed.** Mask as `<redacted>`.
