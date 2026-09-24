import pandas as pd


def average_shipping_days(df: pd.DataFrame) -> float:
    """
    Return overall average shipping duration.
    """
    return df["Shipping Days"].mean()


def shipping_by_mode(df: pd.DataFrame) -> pd.Series:
    """
    Return average shipping days grouped by ship mode.
    """
    return (
        df.groupby("Ship Mode")["Shipping Days"]
        .mean()
        .sort_values()
    )


def shipping_range(df: pd.DataFrame) -> dict:
    """
    Return minimum, maximum and negative shipping duration information.
    """
    return {
        "minimum_days": df["Shipping Days"].min(),
        "maximum_days": df["Shipping Days"].max(),
        "negative_records": int(
            (df["Shipping Days"] < 0).sum()
        )
    }


def orders_by_ship_mode(df: pd.DataFrame) -> pd.Series:
    """
    Return number of records for each shipping mode.
    """
    return df["Ship Mode"].value_counts()