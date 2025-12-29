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


def _extract_scalar_bound(value, use_upper=False):
    """Extract a scalar value from a potential interval bound.

    If the bound is itself an interval (which can happen when mixing libraries),
    extract the appropriate scalar bound from it.
    """
    # If it's our Interval wrapper, get the inner RustInterval
    if hasattr(value, '_inner'):
        value = value._inner

    # If it's a RustInterval, extract the appropriate bound
    if isinstance(value, RustInterval):
        return value.upper if use_upper else value.lower

    # If it's a portion.Interval, extract the appropriate bound
    if isinstance(value, _portion.Interval):
        return value.upper if use_upper else value.lower

    return value


def _from_portion_interval(interval):
    """Convert portion.Interval to RustInterval if needed.

    Returns a RustInterval (not an Interval wrapper) for use in Rust operations.
    """
    # If already a RustInterval, return as-is
    if isinstance(interval, RustInterval):
        return interval

    # If it's our Interval wrapper, extract the inner RustInterval
    if hasattr(interval, '_inner'):
        return interval._inner

    if isinstance(interval, _portion.Interval):
        # Use rust_* functions which are the raw Rust functions (not the wrappers)
        result = rust_empty()
        for atomic in interval:
            lower = _extract_scalar_bound(atomic.lower, use_upper=False)
            upper = _extract_scalar_bound(atomic.upper, use_upper=True)
            left_closed = atomic.left == _portion.CLOSED
            right_closed = atomic.right == _portion.CLOSED

            # Handle infinity
            if lower == -_portion.inf:
                lower = -inf
            if upper == _portion.inf:
                upper = inf

            if left_closed and right_closed:
                result = result | rust_closed(lower, upper)
            elif left_closed:
                result = result | rust_closedopen(lower, upper)
            elif right_closed:
                result = result | rust_openclosed(lower, upper)
            else:
                result = result | rust_open(lower, upper)
        return result
    return interval


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

    Converts RustInterval/Interval to portion.Interval first, then uses portion's to_data.
    """
    # Handle Interval wrapper class
    if hasattr(interval, '_inner'):
        interval = interval._inner
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


# Create wrapper class that handles interoperability with portion.Interval
class Interval:
    """
    Interval class that wraps RustInterval and handles interoperability
    with portion.Interval for seamless mixing of both types.
    """
    __slots__ = ('_inner',)

    def __init__(self, inner=None):
        if inner is None:
            self._inner = empty()
        elif isinstance(inner, Interval):
            self._inner = inner._inner
        elif isinstance(inner, RustInterval):
            self._inner = inner
        elif isinstance(inner, _portion.Interval):
            self._inner = _from_portion_interval(inner)
        else:
            raise TypeError(f"Cannot create Interval from {type(inner)}")

    @classmethod
    def _wrap(cls, rust_interval):
        """Wrap a RustInterval without conversion."""
        obj = object.__new__(cls)
        obj._inner = rust_interval
        return obj

    def _convert_other(self, other):
        """Convert other operand to RustInterval."""
        if isinstance(other, Interval):
            return other._inner
        elif isinstance(other, RustInterval):
            return other
        elif isinstance(other, _portion.Interval):
            return _from_portion_interval(other)
        return other

    # Delegate all operations to inner RustInterval
    def __or__(self, other):
        return Interval._wrap(self._inner | self._convert_other(other))

    def __ror__(self, other):
        return Interval._wrap(self._convert_other(other) | self._inner)

    def __and__(self, other):
        return Interval._wrap(self._inner & self._convert_other(other))

    def __rand__(self, other):
        return Interval._wrap(self._convert_other(other) & self._inner)

    def __sub__(self, other):
        return Interval._wrap(self._inner - self._convert_other(other))

    def __rsub__(self, other):
        return Interval._wrap(self._convert_other(other) - self._inner)

    def __invert__(self):
        return Interval._wrap(~self._inner)

    def __contains__(self, item):
        return item in self._inner

    def __eq__(self, other):
        return self._inner == self._convert_other(other)

    def __ne__(self, other):
        return self._inner != self._convert_other(other)

    def __lt__(self, other):
        return self._inner < self._convert_other(other)

    def __le__(self, other):
        return self._inner <= self._convert_other(other)

    def __gt__(self, other):
        return self._inner > self._convert_other(other)

    def __ge__(self, other):
        return self._inner >= self._convert_other(other)

    def __hash__(self):
        return hash(self._inner)

    def __repr__(self):
        return repr(self._inner)

    def __str__(self):
        return str(self._inner)

    def __bool__(self):
        return bool(self._inner)

    def __iter__(self):
        return iter(self._inner)

    def __len__(self):
        return len(self._inner)

    # Delegate properties and methods
    @property
    def empty(self):
        return self._inner.empty

    @property
    def atomic(self):
        return self._inner.atomic

    @property
    def lower(self):
        return self._inner.lower

    @property
    def upper(self):
        return self._inner.upper

    @property
    def left(self):
        return self._inner.left

    @property
    def right(self):
        return self._inner.right

    @property
    def enclosure(self):
        return Interval._wrap(self._inner.enclosure)

    def union(self, other):
        return self | other

    def intersection(self, other):
        return self & other

    def difference(self, other):
        return self - other

    def complement(self):
        return ~self

    def contains(self, item):
        return item in self

    def overlaps(self, other):
        return self._inner.overlaps(self._convert_other(other))

    def adjacent(self, other):
        return self._inner.adjacent(self._convert_other(other))


# Keep raw Rust functions with _raw suffix for direct access
_raw_open = open
_raw_closed = closed
_raw_openclosed = openclosed
_raw_closedopen = closedopen
_raw_singleton = singleton
_raw_empty = empty


# Override interval creation functions to return Interval wrapper class
def open(lower, upper):
    """Create an open interval (lower, upper)."""
    return Interval._wrap(_raw_open(lower, upper))

def closed(lower, upper):
    """Create a closed interval [lower, upper]."""
    return Interval._wrap(_raw_closed(lower, upper))

def openclosed(lower, upper):
    """Create a half-open interval (lower, upper]."""
    return Interval._wrap(_raw_openclosed(lower, upper))

def closedopen(lower, upper):
    """Create a half-open interval [lower, upper)."""
    return Interval._wrap(_raw_closedopen(lower, upper))

def singleton(value):
    """Create a singleton interval [value]."""
    return Interval._wrap(_raw_singleton(value))

def empty():
    """Create an empty interval ()."""
    return Interval._wrap(_raw_empty())


# Re-export RustBound as Bound
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
    # Interval creation functions (return Interval wrapper)
    "open",
    "closed",
    "openclosed",
    "closedopen",
    "singleton",
    "empty",
    # Raw Rust functions (return RustInterval directly)
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
