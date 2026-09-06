"""Immutable Okapi BM25 article search index."""

from __future__ import annotations

import math
import re
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
    length: int


def fold_plural(term: str) -> str:
    if len(term) < MINIMUM_PLURAL_LENGTH or not term.endswith("s"):
        return term
    if term.endswith(("ss", "us")):
        return term
    return term[:-1]


def tokenize(text: str) -> tuple[str, ...]:
    # Python's \w includes underscore, while Go's letter-or-digit boundary does not.
    fields = (part for part in _TOKEN_BOUNDARY.split(text.lower().replace("_", " ")) if part)
    return tuple(fold_plural(field) for field in fields)


def normalize_search_query(query: str) -> str:
    return query.strip()[:SEARCH_QUERY_LIMIT].strip()


class SearchIndex:
    """Precomputed frequency index that owns its reverse-chronological collection."""

    __slots__ = ("_articles", "_average_length", "_document_frequency", "_documents")

    def __init__(self, articles: tuple[Article, ...]) -> None:
        self._articles = articles
        documents: list[_SearchDocument] = []
        document_frequency: Counter[str] = Counter()
        total = 0
        for article in articles:
            terms: Counter[str] = Counter()
            for text, boost in (
                (article.title, TITLE_BOOST),
                (" ".join(article.tags), TAG_BOOST),
                (article.description, DESCRIPTION_BOOST),
                (article.markdown, BODY_BOOST),
            ):
                terms.update({term: count * boost for term, count in Counter(tokenize(text)).items()})
            length = sum(terms.values())
            documents.append(_SearchDocument(terms, length))
            document_frequency.update(terms.keys())
            total += length
        self._documents = tuple(documents)
        self._document_frequency = document_frequency
        self._average_length = total / len(documents) if documents else 0.0

    @property
    def articles(self) -> tuple[Article, ...]:
        return self._articles

    def search(self, query: str) -> tuple[Article, ...]:
        terms = tuple(sorted(set(tokenize(query))))
        if not terms or not self._documents:
            return ()

        document_count = float(len(self._documents))
        hits: list[tuple[float, int]] = []
        for position, document in enumerate(self._documents):
            score = 0.0
            for term in terms:
                frequency = float(document.terms[term])
                if not frequency:
                    continue
                matches = float(self._document_frequency[term])
                inverse_frequency = math.log(1 + (document_count - matches + 0.5) / (matches + 0.5))
                norm = 1 - BM25_B + BM25_B * document.length / self._average_length
                score += inverse_frequency * (frequency * (BM25_K1 + 1)) / (frequency + BM25_K1 * norm)
            if score > 0:
                hits.append((score, position))
        # Python's sort is stable, so collection order remains the relevance tie-break.
        hits.sort(key=lambda hit: hit[0], reverse=True)
        return tuple(self._articles[position] for _, position in hits)
