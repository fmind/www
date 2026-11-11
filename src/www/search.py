"""Immutable Okapi BM25 article search index."""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from www.models import Article

BM25_K1 = 1.2
BM25_B = 0.75
TITLE_BOOST = 3
TAG_BOOST = 3
DESCRIPTION_BOOST = 2
BODY_BOOST = 1
SEARCH_QUERY_LIMIT = 128
MINIMUM_PLURAL_LENGTH = 4
_TOKEN_BOUNDARY = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class _SearchDocument:
    terms: Counter[str]
    norm: float


def fold_plural(term: str) -> str:
    if len(term) < MINIMUM_PLURAL_LENGTH or not term.endswith("s"):
        return term
    if term.endswith(("ss", "us")):
        return term
    return term[:-1]


def tokenize(text: str) -> tuple[str, ...]:
    # NFKC composes decomposed accents (which \w would split) and folds
    # fullwidth forms; casefold matches "straße" with "STRASSE". Treat
    # underscores as word boundaries rather than part of a search token.
    folded = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    fields = (part for part in _TOKEN_BOUNDARY.split(folded) if part)
    return tuple(fold_plural(field) for field in fields)


def normalize_search_query(query: str) -> str:
    return " ".join(query.split())[:SEARCH_QUERY_LIMIT].rstrip()


class SearchIndex:
    """Precomputed frequency index that owns its reverse-chronological collection."""

    __slots__ = ("_articles", "_document_frequency", "_documents")

    def __init__(self, articles: tuple[Article, ...]) -> None:
        self._articles = articles
        raw_documents: list[tuple[Counter[str], int]] = []
        document_frequency: Counter[str] = Counter()
        total = 0
        for article in articles:
            terms: Counter[str] = Counter()
            for text, boost in (
                (article.title, TITLE_BOOST),
                (" ".join(article.tags), TAG_BOOST),
                (article.description, DESCRIPTION_BOOST),
                (article.search_text, BODY_BOOST),
            ):
                terms.update({term: count * boost for term, count in Counter(tokenize(text)).items()})
            length = sum(terms.values())
            raw_documents.append((terms, length))
            document_frequency.update(terms.keys())
            total += length
        average_length = total / len(raw_documents) if raw_documents else 1.0
        self._documents = tuple(
            _SearchDocument(terms, 1 - BM25_B + BM25_B * length / average_length) for terms, length in raw_documents
        )
        self._document_frequency = document_frequency

    def search(self, query: str) -> tuple[Article, ...]:
        terms = tuple(sorted(set(tokenize(query))))
        if not terms or not self._documents:
            return ()

        document_count = float(len(self._documents))
        weighted_terms = tuple(
            (term, math.log(1 + (document_count - matches + 0.5) / (matches + 0.5)))
            for term in terms
            if (matches := float(self._document_frequency[term]))
        )
        if not weighted_terms:
            return ()

        hits: list[tuple[float, int]] = []
        for position, document in enumerate(self._documents):
            score = 0.0
            for term, inverse_frequency in weighted_terms:
                if frequency := float(document.terms[term]):
                    score += inverse_frequency * (frequency * (BM25_K1 + 1)) / (frequency + BM25_K1 * document.norm)
            if score > 0:
                hits.append((score, position))
        # Python's sort is stable, so collection order remains the relevance tie-break.
        hits.sort(key=lambda hit: hit[0], reverse=True)
        return tuple(self._articles[position] for _, position in hits)
