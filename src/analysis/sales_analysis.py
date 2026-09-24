import pandas as pd


def total_sales(df: pd.DataFrame) -> float:
    """
    Return total sales from the dataset.
    """
    return df["Sales"].sum()


def average_sales(df: pd.DataFrame) -> float:
    """
    Return average sales per row.
    """
    return df["Sales"].mean()


def sales_by_region(df: pd.DataFrame) -> pd.Series:
    """
    Return total sales grouped by region.
    """
    return (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )


def sales_by_category(df: pd.DataFrame) -> pd.Series:
    """
    Return total sales grouped by category.
    """
    return (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )


def sales_by_year(df: pd.DataFrame) -> pd.Series:
    """
    Return total sales grouped by year.
    """
    return (
        df.groupby("Order Year")["Sales"]
        .sum()
        .sort_index()
    )


def yearly_growth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return yearly sales with year-over-year growth percentage.
    """
    yearly_sales = sales_by_year(df)

    growth = yearly_sales.pct_change() * 100

    result = pd.DataFrame({
        "Sales": yearly_sales,
        "Growth %": growth
    })

    return result


def region_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return regional sales and percentage share.
    """
    region_sales = sales_by_region(df)

    share = (
        region_sales / region_sales.sum() * 100
    ).round(2)

    result = pd.DataFrame({
        "Sales": region_sales,
        "Share %": share
    })

    return result


def top_products(
    df: pd.DataFrame,
    n: int = 10
) -> pd.Series:
    """
    Return top N products based on total sales.
    """
    return (
        df.groupby("Product Name")["Sales"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )


def top_customers(
    df: pd.DataFrame,
    n: int = 10
) -> pd.Series:
    """
    Return top N customers based on total sales.
    """
    return (
        df.groupby("Customer Name")["Sales"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )