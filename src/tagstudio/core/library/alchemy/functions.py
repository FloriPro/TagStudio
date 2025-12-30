import logging

from Levenshtein import distance
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)
logger.info("Importing fuzzy matching functions for SQLAlchemy.")


def init_levenshtein():
    @sa_event.listens_for(Engine, "connect")
    def register_levenshtein(dbapi_connection, connection_record):
        try:
            dbapi_connection.create_function("levenshtein", 2, levenshtein)
            dbapi_connection.create_function("part_of_levenshtein", 2, part_of_levenshtein)
            dbapi_connection.create_function("fuzzy_similarity", 2, fuzzy_similarity)
            dbapi_connection.create_function("part_fuzzy_similarity", 2, part_fuzzy_similarity)
        except Exception as e:
            logger.warning("Could not register custom functions: %s", e)


def fuzzy_similarity(element: str, query: str) -> float:
    """Compute a similarity score between 0 and 1 based on Levenshtein distance."""
    if not element or not query:
        return 0.0

    lev_distance = levenshtein(element, query)
    min_len = min(len(element), len(query))
    similarity = 1.0 - (lev_distance / min_len)
    return similarity


def part_fuzzy_similarity(element: str, query: str) -> float:
    """Compute a similarity score between 0 and 1 based on partial Levenshtein distance."""
    if not element or not query:
        return 0.0

    lev_distance = part_of_levenshtein(element, query)
    similarity = 1.0 - (lev_distance / min(len(element), len(query)))
    return similarity


def part_of_levenshtein(element: str, query: str) -> int:
    """Compute the minimum Levenshtein distance between string a and any substring of b."""
    min_distance = 99999
    len_element = len(element)
    len_query = len(query)

    for i in range(len_element - len_query + 1):
        substring = element[i : i + len_query]
        distance = levenshtein(substring, query)
        if distance < min_distance:
            min_distance = distance

    return min_distance


def levenshtein(element: str, query: str) -> int:
    return distance(element, query)
    """Compute the Damerau-Levenshtein distance between two strings (allows transpositions)."""
    len_element = len(element)
    len_query = len(query)
    if len_element == 0:
        return len_query
    if len_query == 0:
        return len_element

    # Initialize matrix
    d = [[0] * (len_query + 1) for _ in range(len_element + 1)]
    for i in range(len_element + 1):
        d[i][0] = i
    for j in range(len_query + 1):
        d[0][j] = j

    for i in range(1, len_element + 1):
        for j in range(1, len_query + 1):
            cost = 0 if element[i - 1] == query[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,  # deletion
                d[i][j - 1] + 1,  # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )
            # Transposition
            if (
                i > 1
                and j > 1
                and element[i - 1] == query[j - 2]
                and element[i - 2] == query[j - 1]
            ):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len_element][len_query]
