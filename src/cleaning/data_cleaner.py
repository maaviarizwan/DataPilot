import pandas as pd


def convert_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert order and ship date columns to datetime.
    """
    df = df.copy()

    df["Order Date"] = pd.to_datetime(
        df["Order Date"],
        dayfirst=True,
        errors="coerce"
    )

    df["Ship Date"] = pd.to_datetime(
        df["Ship Date"],
        dayfirst=True,
        errors="coerce"
    )

    return df


def clean_postal_code(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert postal code to nullable integer type.
    """
    df = df.copy()

    df["Postal Code"] = df["Postal Code"].astype("Int64")

    return df


def add_date_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add useful date-based features.
    """
    df = df.copy()

    df["Order Year"] = df["Order Date"].dt.year
    df["Order Month"] = df["Order Date"].dt.month
    df["Order Month Name"] = df["Order Date"].dt.month_name()
    df["Order Quarter"] = df["Order Date"].dt.quarter
    df["Order Day"] = df["Order Date"].dt.day

    return df


def add_shipping_days(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate number of days between order and shipment.
    """
    df = df.copy()

    df["Shipping Days"] = (
        df["Ship Date"] - df["Order Date"]
    ).dt.days

    return df


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the complete basic data preparation pipeline.
    """
    df = convert_dates(df)
    df = clean_postal_code(df)
    df = add_date_features(df)
    df = add_shipping_days(df)

    return df