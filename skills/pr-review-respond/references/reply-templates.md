# Reply Templates

Copy-paste Markdown skeletons per verdict. Replace `<placeholders>`. When replying outside the original thread, add the source-context block below after the badge; GitHub does not automatically quote the source of a new inline or top-level comment.

## Style rules

- First person, present tense.
- No "Great catch!" / "Excellent point!" filler. Acknowledge, then content.
- Cite `path:line` for every concrete claim.
- 1–3 short paragraphs max. If you're writing more, re-check the verdict.
- Don't disparage. Even on `WRONG`, attack the claim, not the reviewer.
- Don't echo secrets that appeared in the reviewer's comment — redact first.
- **Every reply starts with a shields.io verdict badge** (matches follow-up skill convention).

### Source context outside the original thread

For a new inline comment or top-level fallback, insert this after the badge and before the verdict explanation:

```markdown
> <short, accurate quote of the specific finding being answered>

[Original comment](<source-comment-url>)
```

Choose the quote and source link automatically. Quote only the relevant claim, not the entire aggregated bot report; redact private data and keep code escaping intact. Follow with `path:line` evidence and actual test results when available. Existing threaded replies already retain their source context and may omit this block. Posting still requires confirmation of the final reply and target.

### Verdict badges

Prepend every reply body with the matching badge on its own line, followed by a blank line:

| Verdict | Badge |
|---------|-------|
| CORRECT | `![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)` |
| WRONG | `![Rejected](https://img.shields.io/badge/Status-Rejected-blue)` |
| PARTIAL | `![Partial](https://img.shields.io/badge/Status-Partial-yellow)` |
| STALE | `![Stale](https://img.shields.io/badge/Status-Stale-lightgrey)` |
| LOCKED | `![Locked](https://img.shields.io/badge/Status-Locked-red)` |
| OPINION | `![Noted](https://img.shields.io/badge/Status-Noted-lightgrey)` |
| AMBIGUOUS | `![Needs Info](https://img.shields.io/badge/Status-Needs_Info-orange)` |

---

## `CORRECT`

Reply is drafted AFTER the fix is committed so the SHA is real, not a placeholder.

**SHA must be a clickable markdown link** — bare hashes do NOT auto-link inside review-comment threads. Format:
```
[<short-sha>](https://github.com/<owner>/<repo>/commit/<full-sha>)
```

```
![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)

Agreed. <one-sentence restatement of the bug/risk>.

Fixed in [<short-sha>](https://github.com/<owner>/<repo>/commit/<full-sha>) — <file:line> now <one-sentence summary of the change>.
```

For multi-line / multi-file fixes:
```
![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)

Agreed. <one-sentence restatement>.

Fixed in [<short-sha>](https://github.com/<owner>/<repo>/commit/<full-sha>):
- <file-a:line> — <what changed>
- <file-b:line> — <what changed>
```

If the fix is local-only (not pushed yet), the skill warns the user separately but the reply itself stays as written — by the time the reviewer reads it, the push should be done.

---

## `WRONG`

```
![Rejected](https://img.shields.io/badge/Status-Rejected-blue)

I don't think this reproduces. <file:line> shows <quote 1-2 lines or summarise>, which means <counter-claim>.

<Optional second beat: trace through one extra call site if helpful, with file:line.>

Happy to be wrong — do you have a repro case in mind that I'm missing?
```

The closing question is intentional: it shifts from defending to inviting evidence. If you can't write that closing question honestly (i.e. you're 100% sure they're wrong with zero room), the verdict might still be `WRONG` but state it more directly:

```
![Rejected](https://img.shields.io/badge/Status-Rejected-blue)

This is intentional — <reason>. Tracked at <file:line / commit SHA / plan reference>.
```

---

## `PARTIAL`

Same convention as `CORRECT`: reply is drafted AFTER the alternative fix is committed, and the SHA is a clickable markdown link.

```
![Partial](https://img.shields.io/badge/Status-Partial-yellow)

You're right that <real issue restated>. Their proposed fix would <why their proposal misses though>.

Went with <alternative approach> in [<short-sha>](https://github.com/<owner>/<repo>/commit/<full-sha>) at <file:line>: <one-sentence rationale>.
```

---

## `STALE`

```
![Stale](https://img.shields.io/badge/Status-Stale-lightgrey)

This was changed in <commit-sha> — <file:line> now reads:

<code snippet, 2-5 lines, in a fenced code block>

Mind re-checking against current HEAD?
```

If the GitHub UI is showing an outdated diff (reviewer commented on an old commit):
```
![Stale](https://img.shields.io/badge/Status-Stale-lightgrey)

Looks like you're viewing an earlier commit. <file:line> at HEAD now handles this — re-request review when you have a moment.
```

---

## `LOCKED`

DO NOT POST WITHOUT USER APPROVAL. Surface to user first; only post a draft after the user picks an option.

If the user says "keep current":
```
![Locked](https://img.shields.io/badge/Status-Locked-red)

Holding the current shape here — this <threshold / library / field / scope> was an explicit product/design decision (see <plan-ref or commit-sha>). The trade-off is <one-line summary>, and we accepted it because <reason>. Open to revisit if you have new data.
```

If the user says "change per reviewer":
Use the `CORRECT` template.

If the user says "hybrid":
Use the `PARTIAL` template.

---

## `OPINION`

Holding current shape:
```
![Noted](https://img.shields.io/badge/Status-Noted-lightgrey)

Fair preference. Going to leave this as-is — <one-line reason: consistency with rest of file / minimising diff / etc.>. Open to flipping if it bites later.
```

Deferring to reviewer:
```
![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)

Sure, will swap to <their suggestion>. Cheap to change and reads <slightly better / fine either way>.
```

---

## `AMBIGUOUS`

```
![Needs Info](https://img.shields.io/badge/Status-Needs_Info-orange)

Can you clarify? <one specific question — what scenario, what input, what error message>.
```

Do NOT speculate at length about what they might have meant.

---

## Universal closing rules

- End on substance, not on apology or filler.
- Never end with "let me know if you have any other concerns" — sounds like marketing.
- If you reference a commit you haven't pushed yet, say "in next commit" not a fake SHA.
