"""
Unit tests for src/analysis/data_profiler.py.

Deliberately uses a small synthetic dataset instead of the Superstore
CSV, per project testing policy: the profiler must generalize to
arbitrary datasets, so its tests should not depend on Superstore's
specific columns.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analysis.data_profiler import profile_dataset, summarize_profile


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """
    A tiny synthetic dataset covering every column type the profiler
    should be able to recognize:

    - record_id:      unique per row      -> identifier
    - signup_date:    date-like strings   -> datetime_like_text
    - is_active:      True/False          -> boolean
    - country:        low-cardinality str -> categorical
    - notes:          near-unique text    -> high cardinality
    - plan_type:      single repeated val -> constant
    - monthly_spend:  numeric, has NaNs   -> numeric, with missing values
    """
    return pd.DataFrame(
        {
            "record_id": [f"REC-{i:04d}" for i in range(20)],
            "signup_date": [f"2024-01-{(i % 28) + 1:02d}" for i in range(20)],
            "is_active": [i % 2 == 0 for i in range(20)],
            "country": ["US", "UK", "PK", "US", "UK"] * 4,
            "notes": [f"unique free-text note number {i}" for i in range(20)],
            "plan_type": ["pro"] * 20,
            "monthly_spend": [10.5 * i if i % 5 != 0 else None for i in range(20)],
        }
    )


def test_row_and_column_counts(sample_df):
    profile = profile_dataset(sample_df)
    assert profile.row_count == 20
    assert profile.column_count == 7


def test_identifier_detection(sample_df):
    profile = profile_dataset(sample_df)
    assert "record_id" in profile.identifier_columns


def test_datetime_like_text_detection(sample_df):
    profile = profile_dataset(sample_df)
    assert "signup_date" in profile.datetime_columns


def test_boolean_detection(sample_df):
    profile = profile_dataset(sample_df)
    assert "is_active" in profile.boolean_columns


def test_categorical_detection(sample_df):
    profile = profile_dataset(sample_df)
    assert "country" in profile.categorical_columns


def test_constant_column_detection(sample_df):
    profile = profile_dataset(sample_df)
    assert "plan_type" in profile.constant_columns


def test_high_cardinality_detection():
    # Repeats a handful of values so uniqueness stays high (> 0.5) but
    # below the identifier threshold (0.98) -- otherwise this column
    # would correctly be classified as an identifier instead, since a
    # column that is *fully* unique is ambiguous between "free text" and
    # "identifier" from statistics alone.
    df = pd.DataFrame(
        {
            "free_text": [f"note {i % 30}" for i in range(40)],
            "category": ["a", "b"] * 20,
        }
    )
    profile = profile_dataset(df)
    assert "free_text" in profile.high_cardinality_columns
    assert "category" not in profile.high_cardinality_columns


def test_numeric_and_missing_values(sample_df):
    profile = profile_dataset(sample_df)
    assert "monthly_spend" in profile.numeric_columns
    col = profile.columns["monthly_spend"]
    assert col.missing_count == 4  # i in {0, 5, 10, 15}
    assert col.missing_percentage == pytest.approx(20.0)


def test_duplicate_row_detection():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    profile = profile_dataset(df)
    assert profile.duplicate_row_count == 1


def test_empty_dataframe_raises():
    with pytest.raises(ValueError):
        profile_dataset(pd.DataFrame())


def test_profile_is_json_serializable(sample_df):
    profile = profile_dataset(sample_df)
    # Pydantic's model_dump should succeed with plain JSON-safe types.
    dumped = profile.model_dump()
    assert dumped["row_count"] == 20
    assert isinstance(dumped["columns"], dict)


def test_summarize_profile_runs(sample_df):
    profile = profile_dataset(sample_df)
    text = summarize_profile(profile)
    assert "20" in text
    assert "rows" in text


def test_profiler_on_superstore_like_shape():
    """
    Sanity check against a Superstore-shaped (but tiny, synthetic)
    frame, to make sure real-world-shaped data doesn't break anything --
    without hardcoding a dependency on the actual Superstore CSV file.
    """
    df = pd.DataFrame(
        {
            "Row ID": range(1, 31),
            "Order Date": ["01/02/2017"] * 30,
            "Region": (["West", "East", "Central", "South"] * 8)[:30],
            "Sales": [100.0 + i for i in range(30)],
            "Postal Code": [10001.0] * 28 + [None, None],
        }
    )
    profile = profile_dataset(df)
    assert "Sales" in profile.numeric_columns
    assert "Region" in profile.categorical_columns
    assert profile.columns["Postal Code"].missing_count == 2
