import json
import logging
import time
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from dateutil import parser

from .const import DOMAIN
from .exception import TraktException

LOGGER = logging.getLogger(__name__)

CACHE_EXPIRATION = 480  # 8 minutes


def update_domain_data(hass, key, content):
    if hass.data.get(DOMAIN) and hass.data[DOMAIN].get(key):
        hass.data[DOMAIN][key].update(content)
    else:
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][key] = content


def split(number: int, by: int) -> List[int]:
    size = ceil(number / by)
    res = []
    for i in range(0, size):
        if i + 1 == size:
            rest = number % by
            if rest == 0:
                res.append(by)
            else:
                res.append(rest)
        else:
            res.append(by)
    return res


# It take the days to fetch starting at yesterday because of timezone.
def compute_calendar_args(
    days_to_fetch: int, max_days_per_request: int
) -> List[Tuple[str, int]]:
    group_of_days = split(days_to_fetch, by=max_days_per_request)
    previous_date = datetime.now() - timedelta(1)
    res = []
    for days in group_of_days:
        from_date = previous_date
        res.append((from_date.strftime("%Y-%m-%d"), days))
        previous_date = from_date + timedelta(days)
    return res


def deserialize_json(document: str) -> Dict[str, Any]:
    """
    Deserialize a json returning a better error than JSONDecodeError.
    Returns empty dict for non-JSON responses (HTML errors, empty responses, etc).

    :param document: The json document
    :return: The dictionary
    """
    if not document or not isinstance(document, str):
        return {}

    stripped = document.strip()
    if not stripped or not (stripped.startswith('{') or stripped.startswith('[')):
        LOGGER.warning("Unexpected API response (not JSON): %s", document[:200])
        return {}

    try:
        return json.loads(stripped)
    except json.decoder.JSONDecodeError as e:
        LOGGER.error("Failed to parse JSON from API: %s - Response was: %s", e, document[:500])
        raise TraktException(f"Can't deserialize the following json:\n{document}")


def cache_insert(cache: Dict[str, Any], key: str, value: Any) -> None:
    """
    Insert a value to a cache.

    :param cache: The cache representation
    :param key: The key of the cache
    :param value: The value to store
    :return: The value if it exists and is not expired
    """
    key_time = f"{key}_time"
    cache[key] = value
    cache[key_time] = time.time()


def cache_retrieve(cache: Dict[str, Any], key: str) -> Optional[Any]:
    """
    Retrieve a value from a cache.

    :param cache: The cache representation
    :param key: The key of the cache
    :return: The value if it exists and is not expired
    """
    key_time = f"{key}_time"
    if key in cache:
        if time.time() - cache[key_time] <= CACHE_EXPIRATION:
            return cache[key]
        else:
            cache.pop(key, None)
            cache.pop(key_time, None)
            return None
    else:
        return None


def extract_value_from(data: Dict[str, Any], path: List[str]) -> Any:
    """
    Extract a value from a dictionary following a path. or throw an exception if the path is not valid.
    """
    try:
        for key in path:
            data = data[key]
        return data
    except KeyError:
        raise TraktException(f"Can't extract the value from the following path: {path}")


def parse_utc_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO date string (all dates returned from Trakt) to a datetime object.
    """
    if not date_str:
        return None

    # Replace 'Z' (UTC designator) with '+00:00' for Python < 3.11 compatibility
    cleaned = date_str.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)
