# Search Wiki Evals

Use these pass/fail checks before sending a substantive Confluence answer. If
any check fails, revise once using only the retrieved results.

## Retrieval

- PASS if query terms are focused system, API, team, or process names. FAIL if
  depth instructions such as "deep search" or "think harder" became query text.
- PASS if retrieval depth matches the request. FAIL if the answer needs page
  content but only link snippets were fetched.
- PASS if a clearly named Confluence space was applied with `--space`.

## Grounding

- PASS if every factual claim is supported by a returned title, excerpt,
  heading, or relevant passage.
- PASS if the answer cites the relevant page title and visible URL.
- PASS if uncertainty is explicit when results are weak, conflicting, or absent.

## Answer Shape

- PASS if the response answers the question before adding supporting context.
- PASS if link-only requests remain concise.
- PASS if multi-page answers identify agreement, disagreement, or the likely
  source of truth instead of blending conflicting pages.

## Error Handling

- PASS if config, authentication, or network failures include a concrete next
  step.
- PASS if no results leads to broader-query suggestions rather than invented
  pages.
