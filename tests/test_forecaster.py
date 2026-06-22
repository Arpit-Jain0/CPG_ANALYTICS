"""
tests/test_forecaster.py

Unit tests for the Prophet-based forecaster (no database, no network).

Scenarios
---------
- build_daily_series: joins sales/products/stores correctly and derives
  missing revenue for ONLINE rows.
- build_holidays: parses the calendar CSV and returns the right Prophet format.
- fit_and_forecast: a synthetic seasonal series yields a non-empty, finite
  forecast with the expected columns and a positive yhat.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

prophet = pytest.importorskip("prophet", reason="Prophet not installed")

from src.forecasting.forecaster import (  # noqa: E402
    build_daily_series,
    build_holidays,
    fit_and_forecast,
)

# ── build_daily_series ────────────────────────────────────────────────────────


def test_build_daily_series_joins_correctly():
    """Sales joined with dim_product and dim_store produces a daily series with category/region."""
    sales = pd.DataFrame(
        {
            "transaction_ts": pd.date_range("2024-01-01", periods=5, freq="D").astype(str),
            "store_id": ["S01"] * 5,
            "sku": ["SKU01"] * 5,
            "revenue": [100.0, 120.0, 90.0, 110.0, 130.0],
            "unit_price": [10.0] * 5,
            "quantity": [10] * 5,
        }
    )
    products = pd.DataFrame({"sku": ["SKU01"], "category": ["Beverages"]})
    stores = pd.DataFrame({"store_id": ["S01"], "region": ["NORTHEAST"]})

    daily = build_daily_series({"sales": sales, "products": products, "stores": stores})

    assert list(daily.columns) == ["ds", "category", "region", "y"]
    assert len(daily) == 5
    assert set(daily["category"]) == {"Beverages"}
    assert set(daily["region"]) == {"NORTHEAST"}
    assert daily["y"].sum() == pytest.approx(550.0)


def test_build_daily_series_derives_online_revenue():
    """ONLINE rows with missing revenue use unit_price × quantity."""
    sales = pd.DataFrame(
        {
            "transaction_ts": ["2024-01-01 10:00:00", "2024-01-01 11:00:00"],
            "store_id": ["S01", "S01"],
            "sku": ["SKU01", "SKU01"],
            "revenue": [None, 50.0],  # first row has no revenue (ONLINE)
            "unit_price": [25.0, 50.0],
            "quantity": [4, 1],
        }
    )
    products = pd.DataFrame({"sku": ["SKU01"], "category": ["Snacks"]})
    stores = pd.DataFrame({"store_id": ["S01"], "region": ["WEST"]})

    daily = build_daily_series({"sales": sales, "products": products, "stores": stores})

    # Both transactions on same day → y = 25*4 + 50 = 150
    assert len(daily) == 1
    assert daily["y"].iloc[0] == pytest.approx(150.0)


def test_build_daily_series_drops_unmatched():
    """Rows with no matching SKU or store_id are dropped from the series."""
    sales = pd.DataFrame(
        {
            "transaction_ts": ["2024-01-01", "2024-01-02"],
            "store_id": ["S01", "S99"],  # S99 has no region
            "sku": ["SKU01", "SKU01"],
            "revenue": [10.0, 20.0],
            "unit_price": [10.0, 20.0],
            "quantity": [1, 1],
        }
    )
    products = pd.DataFrame({"sku": ["SKU01"], "category": ["Beverages"]})
    stores = pd.DataFrame({"store_id": ["S01"], "region": ["EAST"]})  # no S99

    daily = build_daily_series({"sales": sales, "products": products, "stores": stores})

    assert len(daily) == 1
    assert daily["y"].iloc[0] == pytest.approx(10.0)


# ── build_holidays ─────────────────────────────────────────────────────────────


def test_build_holidays_filters_holiday_days():
    """Only rows with is_holiday=True appear in the holidays output."""
    cal = pd.DataFrame(
        {
            "calendar_date": ["2024-01-01", "2024-01-02", "2024-07-04"],
            "is_holiday": [True, False, True],
            "holiday_name": ["New Year", None, "Independence Day"],
        }
    )
    holidays = build_holidays(cal)

    assert set(holidays.columns) >= {"holiday", "ds", "lower_window", "upper_window"}
    assert len(holidays) == 2
    assert "New Year" in holidays["holiday"].values
    assert "Independence Day" in holidays["holiday"].values


def test_build_holidays_empty_calendar():
    """A calendar with no holidays returns an empty DataFrame with the right columns."""
    cal = pd.DataFrame(
        {
            "calendar_date": ["2024-01-01"],
            "is_holiday": [False],
            "holiday_name": [None],
        }
    )
    holidays = build_holidays(cal)

    assert len(holidays) == 0
    assert "holiday" in holidays.columns


# ── fit_and_forecast ──────────────────────────────────────────────────────────


def _make_train_df(n_days: int = 70) -> pd.DataFrame:
    """
    Synthetic daily revenue: a trend + weekly seasonality + small noise.
    n_days should be > MIN_HISTORY_DAYS (60) so Prophet doesn't skip the series.
    """
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    rng = np.random.default_rng(42)
    y = (
        100.0  # base
        + np.arange(n_days) * 0.5  # slight upward trend
        + 20.0 * np.sin(2 * np.pi * np.arange(n_days) / 7)  # weekly seasonality
        + rng.normal(0, 5, n_days)  # noise
    )
    y = np.clip(y, 0, None)
    return pd.DataFrame({"ds": dates, "y": y})


def test_fit_and_forecast_non_empty():
    """A seasonal series produces a non-empty forecast DataFrame."""
    train = _make_train_df(70)
    holidays = pd.DataFrame(columns=["holiday", "ds", "lower_window", "upper_window"])
    promo_lookup = {}

    forecast, err = fit_and_forecast(train, holidays, promo_lookup, horizon_days=30)

    assert err is None, f"fit_and_forecast returned error: {err}"
    assert forecast is not None
    assert len(forecast) == 30


def test_fit_and_forecast_finite_values():
    """All forecast values (yhat, bounds) are finite and non-negative."""
    train = _make_train_df(70)
    holidays = pd.DataFrame(columns=["holiday", "ds", "lower_window", "upper_window"])

    forecast, err = fit_and_forecast(train, holidays, {}, horizon_days=10)

    assert forecast is not None
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        assert col in forecast.columns
        assert forecast[col].notna().all(), f"NaN in {col}"
        assert np.isfinite(forecast[col].values).all(), f"Inf in {col}"
        assert (forecast[col] >= 0).all(), f"Negative value in {col}"


def test_fit_and_forecast_returns_only_future():
    """Only dates strictly after the last training date are returned."""
    train = _make_train_df(70)
    max_train = train["ds"].max()
    holidays = pd.DataFrame(columns=["holiday", "ds", "lower_window", "upper_window"])

    forecast, _ = fit_and_forecast(train, holidays, {}, horizon_days=14)

    assert forecast is not None
    assert (forecast["ds"] > max_train).all()


def test_fit_and_forecast_horizon_length():
    """The returned DataFrame has exactly horizon_days rows."""
    train = _make_train_df(65)
    holidays = pd.DataFrame(columns=["holiday", "ds", "lower_window", "upper_window"])

    forecast, _ = fit_and_forecast(train, holidays, {}, horizon_days=7)

    assert forecast is not None
    assert len(forecast) == 7
