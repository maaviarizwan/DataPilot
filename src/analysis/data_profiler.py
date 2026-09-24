"""
Generic dataset profiling for DataPilot.

This module inspects any tabular ``pandas.DataFrame`` -- not just the
Superstore practice dataset -- and produces a structured, serializable
profile describing its shape, column types, data-quality issues, and
per-column statistics.

Design principle (see project spec, section 6 "generic architecture"):
this module must never hardcode business column names such as
"Sales", "Region" or "Category". All type and quality inference is
done from dtypes, value patterns, and cardinality ratios, so the same
code works on an arbitrary dataset the user uploads later.

Typical usage:

    from src.analysis.data_profiler import profile_dataset, summarize_profile

    profile = profile_dataset(df)
    print(summarize_profile(profile))
    profile.model_dump()  # JSON-serializable dict, e.g. for an API response
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tunable heuristics. Centralized here so they can be adjusted or exposed as
# configuration later without touching the detection logic itself.
# ---------------------------------------------------------------------------

#: A column is treated as a likely unique identifier (e.g. "Order ID",
#: "Customer ID", a row key) when the fraction of unique non-null values
#: is at or above this ratio.
IDENTIFIER_UNIQUE_RATIO = 0.98

#: A non-numeric, non-datetime column is flagged "high cardinality" when
#: its unique-value ratio exceeds this threshold. High-cardinality columns
#: (e.g. free-text product names) are usually poor candidates for
#: group-by dimensions or charts.
HIGH_CARDINALITY_RATIO = 0.5

#: ... but only once it has at least this many distinct values -- avoids
#: flagging small categorical columns in small datasets as high cardinality.
HIGH_CARDINALITY_MIN_UNIQUE = 25

#: When sampling an object/string column to test whether it actually holds
#: dates (e.g. "Order Date" before cleaning converts it), this fraction of
#: sampled non-null values must successfully parse as a date.
DATETIME_PARSE_SUCCESS_RATIO = 0.9

#: Max sample size used for the datetime-parse heuristic. Keeps profiling
#: fast on large datasets -- we don't need to parse every row to decide
#: "this column looks like a date".
DATETIME_SAMPLE_SIZE = 200

#: Number of example values to keep per column for quick human inspection.
SAMPLE_VALUES_PER_COLUMN = 5


class ColumnProfile(BaseModel):
    """Profile of a single column."""

    name: str
    pandas_dtype: str
    inferred_type: str = Field(
        description=(
            "One of: numeric, boolean, datetime, datetime_like_text, "
            "categorical, identifier, constant, text."
        )
    )
    missing_count: int
    missing_percentage: float
    unique_count: int
    unique_ratio: float
    is_identifier_like: bool
    is_constant: bool
    is_high_cardinality: bool
    sample_values: list[Any]


class DatasetProfile(BaseModel):
    """Full structural + quality profile of a dataset."""

    row_count: int
    column_count: int
    duplicate_row_count: int
    duplicate_row_percentage: float
    memory_usage_bytes: int

    numeric_columns: list[str]
    categorical_columns: list[str]
    datetime_columns: list[str]
    boolean_columns: list[str]
    identifier_columns: list[str]
    constant_columns: list[str]
    high_cardinality_columns: list[str]

    columns: dict[str, ColumnProfile]

    @property
    def has_quality_issues(self) -> bool:
        """True if there is anything worth surfacing to the user."""
        return bool(
            self.duplicate_row_count
            or self.constant_columns
            or any(c.missing_count for c in self.columns.values())
        )


def _looks_like_datetime_text(series: pd.Series) -> bool:
    """
    Heuristic: does this object/string column actually hold dates that
    just haven't been converted yet (e.g. a freshly-loaded CSV)?

    We sample a bounded number of non-null values and attempt to parse
    them; if most parse successfully, treat the column as a datetime
    candidate. This intentionally runs on a sample, not the full column,
    so profiling stays fast on large datasets.
    """
    non_null = series.dropna()
    if non_null.empty:
        return False

    sample = non_null.sample(
        n=min(DATETIME_SAMPLE_SIZE, len(non_null)), random_state=0
    )
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    success_ratio = parsed.notna().mean()
    return success_ratio >= DATETIME_PARSE_SUCCESS_RATIO


def _infer_column_type(
    series: pd.Series,
    unique_count: int,
    unique_ratio: float,
    is_identifier_like: bool,
    is_constant: bool,
) -> str:
    """Decide the single best-fit semantic type label for a column."""
    if is_constant:
        return "constant"
    if pd.api.types.is_bool_dtype(series.dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series.dtype):
        return "numeric"

    # NOTE: pandas >= 3.0 gives plain string columns a native
    # `StringDtype` ("str") instead of the legacy `object` dtype, so both
    # checks are needed to catch text columns across pandas versions.
    is_textlike = (
        pd.api.types.is_object_dtype(series.dtype)
        or pd.api.types.is_string_dtype(series.dtype)
        or isinstance(series.dtype, pd.CategoricalDtype)
    )
    if is_textlike:
        # Check "looks like a date" before the identifier heuristic: an
        # unconverted date column (e.g. "Order Date" straight from a CSV)
        # is often almost as unique as an identifier, purely because
        # dates have fine granularity -- that uniqueness shouldn't hide
        # the more informative "this is a date" classification.
        if _looks_like_datetime_text(series):
            return "datetime_like_text"
        if is_identifier_like:
            return "identifier"
        return "categorical"

    if is_identifier_like:
        return "identifier"
    return "text"


def _profile_column(series: pd.Series, row_count: int) -> ColumnProfile:
    non_null = series.dropna()
    missing_count = int(row_count - len(non_null))
    unique_count = int(non_null.nunique())
    unique_ratio = (unique_count / row_count) if row_count else 0.0

    is_constant = unique_count <= 1
    is_identifier_like = (
        row_count > 0
        and unique_ratio >= IDENTIFIER_UNIQUE_RATIO
        and not pd.api.types.is_float_dtype(series.dtype)
    )
    is_high_cardinality = (
        not is_identifier_like
        and unique_count >= HIGH_CARDINALITY_MIN_UNIQUE
        and unique_ratio >= HIGH_CARDINALITY_RATIO
        and not pd.api.types.is_numeric_dtype(series.dtype)
    )

    inferred_type = _infer_column_type(
        series, unique_count, unique_ratio, is_identifier_like, is_constant
    )

    sample_values = [
        v.item() if hasattr(v, "item") else v
        for v in non_null.unique()[:SAMPLE_VALUES_PER_COLUMN]
    ]

    return ColumnProfile(
        name=str(series.name),
        pandas_dtype=str(series.dtype),
        inferred_type=inferred_type,
        missing_count=missing_count,
        missing_percentage=round(
            (missing_count / row_count * 100) if row_count else 0.0, 2
        ),
        unique_count=unique_count,
        unique_ratio=round(unique_ratio, 4),
        is_identifier_like=is_identifier_like,
        is_constant=is_constant,
        is_high_cardinality=is_high_cardinality,
        sample_values=sample_values,
    )


def profile_dataset(df: pd.DataFrame) -> DatasetProfile:
    """
    Build a full structural and data-quality profile of ``df``.

    This is dataset-agnostic: it works on the Superstore CSV today and
    on any arbitrary CSV/XLSX a user uploads later, because every
    classification is derived from dtype and value statistics rather
    than known column names.

    Raises:
        ValueError: if ``df`` has no columns at all (nothing to profile).
    """
    if df.shape[1] == 0:
        raise ValueError("Cannot profile a dataset with no columns.")

    row_count = int(df.shape[0])
    column_count = int(df.shape[1])

    columns: dict[str, ColumnProfile] = {}
    for col_name in df.columns:
        columns[str(col_name)] = _profile_column(df[col_name], row_count)

    def names_where(predicate) -> list[str]:
        return [name for name, prof in columns.items() if predicate(prof)]

    numeric_columns = names_where(lambda p: p.inferred_type == "numeric")
    categorical_columns = names_where(lambda p: p.inferred_type == "categorical")
    datetime_columns = names_where(
        lambda p: p.inferred_type in ("datetime", "datetime_like_text")
    )
    boolean_columns = names_where(lambda p: p.inferred_type == "boolean")
    identifier_columns = names_where(lambda p: p.is_identifier_like)
    constant_columns = names_where(lambda p: p.is_constant)
    high_cardinality_columns = names_where(lambda p: p.is_high_cardinality)

    duplicate_row_count = int(df.duplicated().sum())

    return DatasetProfile(
        row_count=row_count,
        column_count=column_count,
        duplicate_row_count=duplicate_row_count,
        duplicate_row_percentage=round(
            (duplicate_row_count / row_count * 100) if row_count else 0.0, 2
        ),
        memory_usage_bytes=int(df.memory_usage(deep=True).sum()),
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        datetime_columns=datetime_columns,
        boolean_columns=boolean_columns,
        identifier_columns=identifier_columns,
        constant_columns=constant_columns,
        high_cardinality_columns=high_cardinality_columns,
        columns=columns,
    )


def summarize_profile(profile: DatasetProfile) -> str:
    """
    Render a short, human-readable summary in the style DataPilot should
    show a user right after upload, e.g.:

        Dataset loaded: 9,800 rows, 18 columns.
        Detected: 1 numeric, 13 categorical, 2 datetime, 0 boolean.
        Data quality: 11 missing values across 1 column(s), 0 duplicate rows.
    """
    total_missing = sum(c.missing_count for c in profile.columns.values())
    columns_with_missing = sum(
        1 for c in profile.columns.values() if c.missing_count
    )

    lines = [
        f"Dataset loaded: {profile.row_count:,} rows, "
        f"{profile.column_count:,} columns.",
        (
            f"Detected: {len(profile.numeric_columns)} numeric, "
            f"{len(profile.categorical_columns)} categorical, "
            f"{len(profile.datetime_columns)} datetime, "
            f"{len(profile.boolean_columns)} boolean."
        ),
        (
            f"Data quality: {total_missing:,} missing value(s) across "
            f"{columns_with_missing} column(s), "
            f"{profile.duplicate_row_count:,} duplicate row(s)."
        ),
    ]

    if profile.identifier_columns:
        lines.append(f"Likely identifiers: {', '.join(profile.identifier_columns)}")
    if profile.constant_columns:
        lines.append(
            f"Constant column(s) (no analytical value): "
            f"{', '.join(profile.constant_columns)}"
        )
    if profile.high_cardinality_columns:
        lines.append(
            f"High-cardinality column(s) (poor chart/group-by candidates): "
            f"{', '.join(profile.high_cardinality_columns)}"
        )

    return "\n".join(lines)
