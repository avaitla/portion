"""
portion_rust - High-performance Rust backend for portion interval library.

This module provides a drop-in replacement for portion with significant
performance improvements for numeric and datetime intervals.

Usage:
    import portion_rust as P  # instead of: import portion as P

    # All standard portion API works:
    interval = P.closed(0, 10) | P.closed(20, 30)
    print(5 in interval)  # True
    print(P.inf > 100)    # True
"""

# Import everything from the native Rust extension
from portion_rust.portion_rust import (
    # Classes
    RustBound,
    RustInterval,
    _PInf,
    _NInf,
    # Functions with rust_ prefix
    rust_open,
    rust_closed,
    rust_openclosed,
    rust_closedopen,
    rust_singleton,
    rust_empty,
    # Functions without prefix (portion API compatible)
    open,
    closed,
    openclosed,
    closedopen,
    singleton,
    empty,
    # Constants
    inf,
    CLOSED,
    OPEN,
)

# Import IntervalDict from portion - it works with portion.Interval
# For RustInterval support, users should convert intervals or use portion's IntervalDict directly
from portion.dict import IntervalDict as _PortionIntervalDict
import portion as _portion

# Re-export utility functions from portion
from portion import to_string, from_string, from_data, iterate


def _to_portion_interval(interval):
    """Convert RustInterval to portion.Interval if needed."""
    if isinstance(interval, RustInterval):
        result = _portion.empty()
        repr_str = repr(interval)
        if repr_str == "()":
            return _portion.empty()

        for part in repr_str.split(" | "):
            part = part.strip()
            if not part or part == "()":
                continue

            left_closed = part[0] == "["
            right_closed = part[-1] == "]"
            inner = part[1:-1]

            if "," not in inner:
                val = _parse_value(inner)
                result = result | _portion.singleton(val)
            else:
                lower_str, upper_str = inner.split(",", 1)
                lower = _parse_value(lower_str)
                upper = _parse_value(upper_str)

                if left_closed and right_closed:
                    result = result | _portion.closed(lower, upper)
                elif left_closed:
                    result = result | _portion.closedopen(lower, upper)
                elif right_closed:
                    result = result | _portion.openclosed(lower, upper)
                else:
                    result = result | _portion.open(lower, upper)

        return result
    return interval


def _parse_value(s):
    """Parse a value from string representation."""
    s = s.strip()
    if s == "-inf":
        return -_portion.inf
    elif s == "+inf":
        return _portion.inf
    elif s.startswith("dt("):
        from datetime import datetime, timezone
        dt_str = s[3:-1]
        if "." in dt_str:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
        else:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    else:
        try:
            return float(s)
        except ValueError:
            return s


def to_data(interval, *, conv=None, pinf=None, ninf=None):
    """
    Export interval to a list of 4-tuples (left, lower, upper, right).

    Converts RustInterval to portion.Interval first, then uses portion's to_data.
    """
    portion_interval = _to_portion_interval(interval)
    return _portion.to_data(portion_interval, conv=conv, pinf=pinf, ninf=ninf)


class IntervalDict(_PortionIntervalDict):
    """
    IntervalDict that works with both RustInterval and portion.Interval.

    Note: This uses portion's IntervalDict internally with automatic conversion.
    For maximum performance with large interval dictionaries, consider using
    portion.IntervalDict directly with portion.Interval.
    """

    def __setitem__(self, key, value):
        super().__setitem__(_to_portion_interval(key), value)

    def __getitem__(self, key):
        return super().__getitem__(_to_portion_interval(key))

    def __delitem__(self, key):
        super().__delitem__(_to_portion_interval(key))

    def __contains__(self, key):
        return super().__contains__(_to_portion_interval(key))


# Re-export Interval as alias for RustInterval
Interval = RustInterval
Bound = RustBound

__all__ = [
    # Classes
    "Interval",
    "RustInterval",
    "Bound",
    "RustBound",
    "IntervalDict",
    "_PInf",
    "_NInf",
    # Interval creation functions
    "open",
    "closed",
    "openclosed",
    "closedopen",
    "singleton",
    "empty",
    "rust_open",
    "rust_closed",
    "rust_openclosed",
    "rust_closedopen",
    "rust_singleton",
    "rust_empty",
    # Utility functions
    "to_data",
    "from_data",
    "to_string",
    "from_string",
    "iterate",
    # Constants
    "inf",
    "CLOSED",
    "OPEN",
]
