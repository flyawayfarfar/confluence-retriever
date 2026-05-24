"""Scorer invariant property tests.

Passing tests encode stable guarantees of the scorer.
xfail tests document current bugs that become fixed in later phases.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import wiki_answer as wiki


def _result(
    *,
    title: str = "",
    excerpt: str = "",
    space_key: str = "XX",
    title_hit: bool = False,
    last_modified: str = "",
) -> dict:
    return {
        "id": "1",
        "title": title,
        "excerpt": excerpt,
        "space_key": space_key,
        "space_name": "Test Space",
        "url": "https://example.com",
        "_title_hit": title_hit,
        "last_modified": last_modified,
    }


# ── Invariants that pass today ────────────────────────────────────────────────

class TestBasicScorerInvariants:
    def test_title_phrase_match_outranks_excerpt_only(self):
        """A page with the query in the title always beats excerpt-only."""
        title_page = _result(title="authentication guide")
        excerpt_page = _result(excerpt="guide to authentication")
        t = wiki.score_result(title_page, ["authentication"], None)
        e = wiki.score_result(excerpt_page, ["authentication"], None)
        assert t > e

    def test_multi_token_all_match_beats_single_token(self):
        """A page matching all query tokens outranks one matching only one."""
        full = _result(title="deploy authentication service")
        partial = _result(title="deploy guide")
        q = ["deploy authentication"]
        assert wiki.score_result(full, q, None) > wiki.score_result(partial, q, None)

    def test_space_match_adds_exactly_1(self):
        """Space key match contributes exactly +1 to score."""
        base = _result(space_key="OTHER", excerpt="authentication")
        same_space = _result(space_key="MT", excerpt="authentication")
        b = wiki.score_result(base, ["authentication"], "MT")
        s = wiki.score_result(same_space, ["authentication"], "MT")
        assert s - b == 1

    def test_no_match_scores_zero(self):
        r = _result(title="completely unrelated topic")
        assert wiki.score_result(r, ["authentication"], None) == 0

    def test_rank_results_preserves_order_on_tie(self):
        """Equal-score results preserve their original relative order."""
        a = {**_result(title="a page"), "id": "a"}
        b = {**_result(title="b page"), "id": "b"}
        ranked = wiki.rank_results([a, b], ["something else"], None)
        assert [r["id"] for r in ranked] == ["a", "b"]

    def test_title_hit_bonus_applied_in_enhanced_mode(self):
        """_title_hit=True adds a score bonus only when enhanced=True."""
        no_hit = _result(title="auth guide", title_hit=False)
        with_hit = _result(title="auth guide", title_hit=True)
        q = ["auth"]
        assert wiki.score_result(no_hit, q, None, enhanced=False) == \
               wiki.score_result(with_hit, q, None, enhanced=False)
        assert wiki.score_result(with_hit, q, None, enhanced=True) > \
               wiki.score_result(no_hit, q, None, enhanced=True)

    def test_proximity_bonus_for_two_distinct_tokens(self):
        """Two distinct tokens close together trigger the proximity bonus."""
        assert wiki._proximity_bonus("deploy authentication here", ["deploy", "authentication"]) == 2

    def test_proximity_no_bonus_when_tokens_far_apart(self):
        """Tokens separated by > 50 chars do not trigger the proximity bonus."""
        far = "deploy " + "x " * 30 + "authentication"
        assert wiki._proximity_bonus(far, ["deploy", "authentication"]) == 0


# ── Phase D: _proximity_bonus same-token false positive ──────────────────────

class TestProximityPhaseD:
    def test_proximity_does_not_trigger_on_single_repeated_token(self):
        """A single token repeated close together must NOT trigger the proximity bonus."""
        assert wiki._proximity_bonus("auth and auth again", ["auth"]) == 0

    def test_proximity_returns_zero_for_single_token_list(self):
        """A query with only one distinct token can never yield a proximity bonus."""
        assert wiki._proximity_bonus("authentication is required for auth", ["auth"]) == 0


# ── Phase I: multiplicative recency ──────────────────────────────────────────

class TestRecencyPhaseI:
    @pytest.mark.xfail(strict=True, reason="enabled by Phase I: multiplicative recency")
    def test_additive_recency_does_not_boost_zero_relevance_page(self):
        """Freshness must not push a zero-relevance page above a relevant page.

        Current bug: additive `score += int(10 * exp(-age/halflife))` adds up to +10
        even when the base score is 0, inverting the ranking for fresh irrelevant pages.

        With multiplicative `score *= exp(-age/halflife)`: 0 * anything = 0, so a
        zero-relevance fresh page stays at 0 and the relevant older page wins.
        """
        zero_relevance_fresh = _result(
            title="weekly meeting notes",
            excerpt="standup summary",
            last_modified="2026-05-24T00:00:00Z",  # today
        )
        medium_relevance_old = _result(
            title="authentication guide",
            excerpt="auth setup steps",
            last_modified="2026-03-25T00:00:00Z",  # ~60 days ago
        )
        z = wiki.score_result(zero_relevance_fresh, ["authentication"], None,
                               enhanced=True, halflife_days=30)
        r = wiki.score_result(medium_relevance_old, ["authentication"], None,
                               enhanced=True, halflife_days=30)
        # With additive recency, z ≈ 10 and r ≈ 9 → z > r (wrong).
        # With multiplicative recency, z = 0 and r > 0 → correct.
        assert r > z

    @pytest.mark.xfail(strict=True, reason="enabled by Phase I: multiplicative recency")
    def test_huge_halflife_matches_no_halflife_score(self):
        """Recency with halflife → ∞ should not change scores at all.

        Current bug: additive recency with halflife=9999999 still adds
        int(10 * exp(-age/9999999)) ≈ 10 to every scored page, drifting from
        the no-halflife baseline.

        With multiplicative: score * exp(-age/9999999) ≈ score * 1 = score.
        """
        r = _result(title="authentication guide", last_modified="2020-01-01T00:00:00Z")
        q = ["authentication"]
        no_recency = wiki.score_result(r, q, None, enhanced=True, halflife_days=None)
        huge_halflife = wiki.score_result(r, q, None, enhanced=True, halflife_days=9999999)
        assert no_recency == huge_halflife
