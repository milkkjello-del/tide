"""Instrumental version finder for the "mute lyrics" karaoke toggle.

Given a vocal track, scan every enabled source for a karaoke /
instrumental cut of the same song and return the best match. We're
matching on what humans match on: title contains an "instrumental"
keyword, artist string overlaps, and the duration is close enough to
the original that the swap won't strand the playhead in dead air.

Cross-source: a YT Music track might have its best instrumental on
SoundCloud, or vice versa. We search every enabled source whose
`search_songs` capability is wired and rank a single shortlist by score.

This module is pure logic — no Qt, no I/O ordering. The caller (the UI)
drives it from a worker thread.
"""
from __future__ import annotations

from dataclasses import dataclass

from .sources import Track, registry as source_registry


# Keywords whose presence in a track title strongly suggests it's an
# instrumental / karaoke cut. Lowercased; whole-word boundary matched.
# Split into two tiers: "instrumental" cuts (more likely an official
# stem) and "karaoke" cuts (more likely a third-party cover). The
# scoring prefers the first tier.
_INSTRUMENTAL_KEYWORDS = (
    "instrumental",
    "instrumentals",
    "off vocal",
    "off vocals",
    "no vocals",
    "no vocal",
    "music only",
    "backing track",
    "minus one",
)
_KARAOKE_KEYWORDS = (
    "karaoke",
    "sing-along",
    "sing along",
)

# Artist-string tokens that almost always indicate a karaoke cover
# channel rather than the original performer. When any of these appear
# in the candidate's artist string AND the candidate's artist doesn't
# strongly overlap the query, we drop the match.
_KARAOKE_CHANNEL_TOKENS = (
    "karafun",
    "sing king",
    "stingray karaoke",
    "starsongs",
    "the karaoke channel",
    "polish your performance",
    "karaoke version",
    "ameritz",
    "redtune",
    "easy karaoke",
    "killer tracks",
    "party tyme karaoke",
    "tracks planet",
    "karaoke heaven",
    "uppermost",
)

# Duration tolerance for swap. Beyond this, the swap risks landing the
# playhead in dead air (instrumental shorter) or mid-fade (longer).
DURATION_TOLERANCE_SECS = 8

# Minimum acceptable score across the weighted criteria. Higher = stricter.
MIN_SCORE_DEFAULT = 0.7
# Below this title overlap we won't pick even an "instrumental"-titled
# candidate, because the song itself is too far off to trust the swap.
MIN_TITLE_OVERLAP = 0.6
# Below this artist overlap (when the candidate doesn't have an unusually
# strong title match) we won't trust the swap to be by the original
# performer.
MIN_ARTIST_OVERLAP = 0.4


@dataclass
class InstrumentalMatch:
    track: Track
    score: float
    source_slug: str
    source_name: str


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _title_has_instrumental_keyword(title: str) -> bool:
    """Either an instrumental-style or karaoke-style keyword counts as a
    valid candidate marker. Use _instrumental_tier() to discriminate
    between the two during scoring."""
    n = _normalize(title)
    return any(k in n for k in _INSTRUMENTAL_KEYWORDS + _KARAOKE_KEYWORDS)


def _instrumental_tier(title: str) -> str:
    """Return ``"instrumental"`` (likely official), ``"karaoke"``
    (likely third-party), or ``""`` (no marker)."""
    n = _normalize(title)
    if any(k in n for k in _INSTRUMENTAL_KEYWORDS):
        return "instrumental"
    if any(k in n for k in _KARAOKE_KEYWORDS):
        return "karaoke"
    return ""


def _is_karaoke_channel(artist: str) -> bool:
    """True when the candidate's listed artist matches a known karaoke
    channel — they're cover producers, not the original performer, and
    the swap would feel wrong even if other signals matched."""
    n = _normalize(artist)
    return any(tok in n for tok in _KARAOKE_CHANNEL_TOKENS)


def _artist_overlap(query_artist: str, candidate_artist: str) -> float:
    """Return a similarity score (0.0–1.0) between two artist strings.

    Handles common multi-artist join formats (``feat.``, commas, &) by
    splitting and counting overlapping tokens. We don't need fuzzy
    matching; if the canonical artist of the original track isn't
    anywhere in the candidate's artist string, it's almost certainly a
    cover or a re-record by someone else and the swap would be wrong.
    """
    q = _normalize(query_artist)
    c = _normalize(candidate_artist)
    if not q or not c:
        return 0.0
    # Quick path: exact substring containment goes a long way.
    if q in c:
        return 1.0
    # Token-set overlap.
    q_tokens = set(t for t in q.replace(",", " ").replace("&", " ").split() if len(t) > 1)
    c_tokens = set(t for t in c.replace(",", " ").replace("&", " ").split() if len(t) > 1)
    if not q_tokens or not c_tokens:
        return 0.0
    inter = len(q_tokens & c_tokens)
    return inter / max(len(q_tokens), len(c_tokens))


def _title_overlap(query_title: str, candidate_title: str) -> float:
    """How much of the original track's title shows up in the candidate.

    Strips parenthesized qualifiers and known instrumental/karaoke
    keywords from the candidate before comparing — those are tags we
    *want* in the candidate but don't want skewing the song-identity
    check. Returns 1.0 only when the cleaned candidate is a token-for-
    token match for the query (modulo order). Asymmetric mismatch is
    captured via a harmonic mean so "Foreword" vs "Foreword Speech
    Instrumental" lands well below 1.0 instead of scoring as a perfect
    match because the substring is there.
    """
    q = _normalize(query_title)
    c = _normalize(candidate_title)
    if not q or not c:
        return 0.0

    def _strip_parens(text: str) -> str:
        out: list[str] = []
        depth = 0
        for ch in text:
            if ch in "([{":
                depth += 1
                continue
            if ch in ")]}" and depth > 0:
                depth -= 1
                continue
            if depth == 0:
                out.append(ch)
        return "".join(out)

    def _drop_keywords(text: str) -> str:
        for kw in _INSTRUMENTAL_KEYWORDS + _KARAOKE_KEYWORDS:
            text = text.replace(kw, " ")
        # Drop common separator words too — they show up in titles like
        # "Foreword - Instrumental" without carrying song identity.
        for sep in (" - ", " — ", "  "):
            text = text.replace(sep, " ")
        return text

    q_clean = _normalize(_drop_keywords(_strip_parens(q)))
    c_clean = _normalize(_drop_keywords(_strip_parens(c)))
    if not q_clean or not c_clean:
        return 0.0

    q_tokens = [t for t in q_clean.split() if len(t) > 1]
    c_tokens = set(t for t in c_clean.split() if len(t) > 1)
    if not q_tokens or not c_tokens:
        return 0.0

    q_in_c = sum(1 for t in q_tokens if t in c_tokens) / len(q_tokens)
    c_in_q = (
        sum(1 for t in c_tokens if t in q_tokens) / max(1, len(c_tokens))
    )
    if q_in_c == 0 or c_in_q == 0:
        return 0.0
    # Harmonic mean — penalizes "query is a prefix of candidate" so
    # "Loud" can't score 1.0 on "Loudspeaker".
    return 2 * q_in_c * c_in_q / (q_in_c + c_in_q)


def _duration_score(query_secs: int, candidate_secs: int) -> float:
    """1.0 when within tolerance and falling linearly to 0.0 at 3x
    tolerance. Beyond 3x, score is 0 — we won't pick something whose
    runtime is dramatically off."""
    if query_secs <= 0 or candidate_secs <= 0:
        return 0.5   # unknown duration is neutral, not disqualifying
    diff = abs(int(query_secs) - int(candidate_secs))
    if diff <= DURATION_TOLERANCE_SECS:
        return 1.0
    hard_cap = DURATION_TOLERANCE_SECS * 3
    if diff >= hard_cap:
        return 0.0
    return 1.0 - (diff - DURATION_TOLERANCE_SECS) / (hard_cap - DURATION_TOLERANCE_SECS)


def _score_candidate(query: Track, candidate: Track) -> float:
    """Aggregate score in [0, 1]. Above MIN_SCORE_DEFAULT we trust the
    swap. Hard rejections (return 0.0) protect against the "random
    karaoke cover slipped through" failure mode the v1.2.1 first cut
    was vulnerable to.

    Weights:
      - 0.40 title overlap (the song-identity check)
      - 0.25 artist overlap (the performer-identity check; raised
        relative to the first cut)
      - 0.20 keyword: instrumental > karaoke. Official instrumental
        cuts trump karaoke covers when both are available.
      - 0.15 duration proximity (tightened tolerance, see constants)

    Hard rejects (overrides everything):
      - candidate's listed artist matches a known karaoke channel AND
        the artist-overlap with the query is weak: it's a cover, not
        the official cut.
      - title overlap below MIN_TITLE_OVERLAP: probably a different
        song that happens to be titled "(Instrumental)".
      - artist overlap below MIN_ARTIST_OVERLAP AND title overlap less
        than near-perfect: probably a cover of an unrelated track
        whose name overlaps loosely.
    """
    title_w = _title_overlap(query.title, candidate.title)
    artist_w = _artist_overlap(query.artists, candidate.artists)
    dur_w = _duration_score(int(query.duration_seconds or 0),
                            int(candidate.duration_seconds or 0))
    tier = _instrumental_tier(candidate.title)
    if tier == "instrumental":
        keyword_w = 1.0
    elif tier == "karaoke":
        keyword_w = 0.55       # weaker than a proper instrumental tag
    else:
        keyword_w = 0.0

    # Hard rejects.
    if _is_karaoke_channel(candidate.artists or "") and artist_w < 0.6:
        return 0.0
    if title_w < MIN_TITLE_OVERLAP:
        return 0.0
    if artist_w < MIN_ARTIST_OVERLAP and title_w < 0.92:
        return 0.0

    return (
        0.40 * title_w
        + 0.25 * artist_w
        + 0.20 * keyword_w
        + 0.15 * dur_w
    )


def find_instrumental(query: Track, *, min_score: float = MIN_SCORE_DEFAULT,
                      per_source_limit: int = 10) -> InstrumentalMatch | None:
    """Search every enabled source for an instrumental of ``query``.

    Returns the highest-scoring match whose score crosses ``min_score``,
    or None if no source surfaces a good enough candidate.

    Blocking — meant to be called from a worker thread.
    """
    if query is None or not (query.title or "").strip():
        return None
    reg = source_registry()
    candidates: list[tuple[float, Track, object]] = []

    # Two queries per source: "{title} {artist} instrumental" and
    # "{title} {artist} karaoke". Some catalogs index one keyword far
    # better than the other.
    qa = (query.artists or "").split(",")[0].strip()
    queries = (
        f"{query.title} {qa} instrumental".strip(),
        f"{query.title} {qa} karaoke".strip(),
    )
    seen_ids: set[str] = set()
    seen_ids.add(query.video_id or "")

    for source in reg.enabled_sources():
        # Skip the source we already know can't search.
        try:
            for q in queries:
                results = source.search_songs(q, limit=per_source_limit) or []
                for cand in results:
                    if not cand or not cand.video_id:
                        continue
                    if cand.video_id in seen_ids:
                        continue
                    seen_ids.add(cand.video_id)
                    if not _title_has_instrumental_keyword(cand.title or ""):
                        continue
                    score = _score_candidate(query, cand)
                    if score >= min_score:
                        candidates.append((score, cand, source))
        except Exception:
            # Search can fail (API down, source mis-configured) — skip
            # this source rather than aborting the whole hunt.
            continue

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    score, track, source = candidates[0]
    return InstrumentalMatch(
        track=track,
        score=score,
        source_slug=getattr(source, "slug", "") or "",
        source_name=getattr(source, "name", "") or "",
    )
