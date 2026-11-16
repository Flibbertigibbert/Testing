"""
Order value forecasting pipeline.

One file, used by both the notebook (forecast.ipynb) and the Streamlit app (app.py),
so the code shown in the app is exactly the code that produced the numbers.

Steps
  1. load_data            read the quote/order CSV
  2. build_features       one row per month, every feature known at the start of that month
  3. design_matrix        turn features into (X, y) for a given forecast horizon h
  4. run_backtest         train/test all 11 models at every horizon (walk-forward)
  5. score_table          compare models: train vs test, per approach (H1, H3, H6)
  6. final_forecast       forecast the next 6 months with the best model per approach

Run `python forecast_pipeline.py` to rebuild everything into ./outputs/
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")

DATA_FILE = Path(__file__).with_name("complete_opp_order_quote.csv")
OUT_DIR = Path(__file__).with_name("outputs")

LARGE = 1_000_000            # orders at or above this are "large"
MATURE_LAG = 9               # quotes this many months old have had time to convert (max observed lag = 8)
LARGE_WINDOW = 36            # months used to estimate the expected large-order amount
TRAIN_START = pd.Timestamp("2021-10-01")   # first month with all features available
TEST_START = pd.Timestamp("2025-01-01")    # first month forecast out-of-sample
APPROACHES = {"H1": 1, "H3": 3, "H6": 6}   # approach name -> number of months ahead


# --------------------------------------------------------------------------------------
# 1. Load
# --------------------------------------------------------------------------------------
def load_data(path: str | Path = DATA_FILE) -> pd.DataFrame:
    """Read the quote-level CSV. One row per quote; order columns are filled only when the quote became an order."""
    return pd.read_csv(
        path,
        dtype={"order_number": "string"},
        parse_dates=["opp_creation_date", "quote_creation_date", "quote_expiry_date", "order_date_month"],
    )


# --------------------------------------------------------------------------------------
# 2. Features
# --------------------------------------------------------------------------------------
def _ratio(num, den):
    return num / den if den > 0 else np.nan


def _in_window(dates, month, start_back, end_back=0):
    """dates in [month - start_back months, month - end_back months)"""
    return (dates >= month - pd.DateOffset(months=start_back)) & (dates < month - pd.DateOffset(months=end_back))


def build_features(df: pd.DataFrame, extra_months: int = 2) -> tuple[pd.DataFrame, pd.Timestamp]:
    """
    Build the monthly feature table. Row M only uses information available at the START of month M.
    Returns (features, last_actual_month).
    """
    orders = df[df["order_number"].notna()].drop_duplicates("order_number").copy()
    orders["is_large"] = orders["order_value"] >= LARGE
    last_actual = orders["order_date_month"].max()
    months = pd.date_range("2020-01-01", last_actual + pd.DateOffset(months=extra_months), freq="MS")

    def monthly_sum(frame, date_col, value_col):
        return frame.groupby(date_col)[value_col].sum().reindex(months, fill_value=0)

    feat = pd.DataFrame(index=months)
    feat.index.name = "month"

    # ---- targets ----
    feat["order_value"] = monthly_sum(orders, "order_date_month", "order_value")
    feat["n_orders"] = orders.groupby("order_date_month").size().reindex(months, fill_value=0)
    feat["regular_value"] = monthly_sum(orders[~orders["is_large"]], "order_date_month", "order_value")
    feat["large_value"] = feat["order_value"] - feat["regular_value"]
    feat["log_order_value"] = np.log1p(feat["order_value"])
    targets = ["order_value", "n_orders", "regular_value", "large_value", "log_order_value"]
    feat.loc[feat.index > last_actual, targets] = np.nan

    # ---- calendar ----
    feat["month_num"] = feat.index.month
    feat["quarter"] = feat.index.quarter
    feat["month_in_qtr"] = (feat.index.month - 1) % 3 + 1
    feat["is_qtr_start"] = (feat["month_in_qtr"] == 1).astype(int)
    feat["is_year_end"] = (feat.index.month == 12).astype(int)
    feat["trend"] = np.arange(len(feat))

    # ---- past orders (shift(1) = only months before M) ----
    for col in ["order_value", "regular_value", "n_orders"]:
        for lag in [1, 2, 3, 12]:
            feat[f"{col}_lag{lag}"] = feat[col].shift(lag)
        past = feat[col].shift(1)
        for w in [3, 6, 12]:
            feat[f"{col}_roll_mean{w}"] = past.rolling(w, min_periods=w).mean()
        feat[f"{col}_roll_median12"] = past.rolling(12, min_periods=12).median()
    feat["regular_value_same_mq_mean"] = feat.groupby("month_in_qtr")["regular_value"].transform(
        lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    large_cnt = orders[orders["is_large"]].groupby("order_date_month").size().reindex(months, fill_value=0)
    feat["large_count_roll12"] = large_cnt.shift(1).rolling(12, min_periods=12).sum()
    feat["large_value_roll12"] = feat["large_value"].shift(1).rolling(12, min_periods=12).sum()

    # ---- pipeline (main quote per revision, to avoid double counting) ----
    q = df[df["quote_to_consider"] == "Y"].copy()
    q["quote_month"] = q["quote_creation_date"].dt.to_period("M").dt.to_timestamp()

    def open_quotes(month, window):
        created = _in_window(q["quote_month"], month, window)
        not_yet_ordered = q["order_date_month"].isna() | (q["order_date_month"] >= month)
        return q[created & not_yet_ordered]

    for w in [3, 6]:
        sel = [open_quotes(m, w) for m in months]
        feat[f"open_quotes_n_{w}m"] = [len(s) for s in sel]
        feat[f"open_quotes_value_{w}m"] = [s["quote_net_amount"].sum() for s in sel]

    new_q = q.groupby("quote_month").agg(n=("quote_key", "size"), value=("quote_net_amount", "sum")).reindex(months, fill_value=0)
    feat["new_quotes_n_lag1"] = new_q["n"].shift(1)
    feat["new_quotes_value_lag1"] = new_q["value"].shift(1)
    opps = df.drop_duplicates("opp_id").copy()
    opps["opp_month"] = opps["opp_creation_date"].dt.to_period("M").dt.to_timestamp()
    new_o = opps.groupby("opp_month").agg(n=("opp_id", "size"), value=("opp_value", "sum")).reindex(months, fill_value=0)
    feat["new_opps_n_lag1"] = new_o["n"].shift(1)
    feat["new_opps_value_lag1"] = new_o["value"].shift(1)
    feat.loc[feat.index < "2020-07-01", [c for c in feat if c.startswith("open_quotes")]] = np.nan

    # ---- conversion, realization, discount, gross margin ----
    o = orders.copy()
    o["quote_month"] = o["quote_creation_date"].dt.to_period("M").dt.to_timestamp()
    o["months_to_order"] = ((o["order_date_month"].dt.year - o["quote_month"].dt.year) * 12
                            + (o["order_date_month"].dt.month - o["quote_month"].dt.month))
    rows = []
    for m in months:
        r = {}
        for w in [6, 12]:                                        # conversion: flow ratio
            ow, qw = o[_in_window(o["order_date_month"], m, w)], q[_in_window(q["quote_month"], m, w)]
            r[f"conv_flow_n_{w}m"] = _ratio(len(ow), len(qw))
            r[f"conv_flow_value_{w}m"] = _ratio(ow["order_value"].sum(), qw["quote_net_amount"].sum())
        cohort = q[_in_window(q["quote_month"], m, MATURE_LAG + 12, MATURE_LAG)]   # conversion: mature cohort
        won = cohort["order_date_month"].notna() & (cohort["order_date_month"] < m)
        r["conv_cohort_n"] = _ratio(won.sum(), len(cohort))
        r["conv_cohort_value"] = _ratio(cohort.loc[won, "quote_net_amount"].sum(), cohort["quote_net_amount"].sum())
        for w in [3, 6, 12]:                                     # realization, discount, margin
            ow = o[_in_window(o["order_date_month"], m, w)]
            ov = ow["order_value"].sum()
            r[f"realization_quote_{w}m"] = _ratio(ov, ow["quote_net_amount"].sum())
            r[f"discount_pct_{w}m"] = _ratio(ow["discount_amount"].sum(), ov + ow["discount_amount"].sum())
            r[f"gm_pct_{w}m"] = _ratio(ow["gross_margin"].sum(), ov)
        o12 = o[_in_window(o["order_date_month"], m, 12)]
        r["realization_list_12m"] = _ratio(o12["order_value"].sum(), o12["quote_list_price"].sum())
        r["realization_opp_12m"] = _ratio(o12["order_value"].sum(), o12["opp_value"].sum())
        r["avg_order_size_12m"] = _ratio(o12["order_value"].sum(), len(o12))
        r["avg_months_to_order_12m"] = o12["months_to_order"].mean() if len(o12) else np.nan
        o1 = o[_in_window(o["order_date_month"], m, 1)]
        r["gm_value_lag1"] = o1["gross_margin"].sum()
        r["discount_value_lag1"] = o1["discount_amount"].sum()
        r["gm_value_roll12"] = o12["gross_margin"].sum()
        open6, new1 = open_quotes(m, 6), q[_in_window(q["quote_month"], m, 1)]
        r["open_quotes_discount_pct_6m"] = 1 - _ratio(open6["quote_net_amount"].sum(), open6["quote_list_price"].sum())
        r["new_quotes_discount_pct_lag1"] = 1 - _ratio(new1["quote_net_amount"].sum(), new1["quote_list_price"].sum())
        rows.append(r)
    ratios = pd.DataFrame(rows, index=months)
    ratios["expected_pipeline_value"] = feat["open_quotes_value_6m"] * ratios["conv_cohort_value"] * ratios["realization_quote_12m"]
    ratios.loc[ratios.index < "2021-10-01", ["conv_cohort_n", "conv_cohort_value", "expected_pipeline_value"]] = np.nan
    feat = feat.join(ratios)

    # Months more than 1 step past the data depend on activity not seen yet -> unknown, not zero
    unseen = feat.index > last_actual + pd.DateOffset(months=1)
    feat.loc[unseen, [c for c in feat if c not in targets and not c.startswith(
        ("month_num", "quarter", "month_in_qtr", "is_", "trend"))]] = np.nan
    return feat, last_actual


TARGET_COLS = ["order_value", "n_orders", "regular_value", "large_value", "log_order_value"]


# --------------------------------------------------------------------------------------
# 3. Design matrix for horizon h (direct forecasting)
# --------------------------------------------------------------------------------------
# Features the ML models use. "At origin" features come from the last row known when the forecast is made.
ORIGIN_FEATURES = ["regular_value_roll_mean12", "open_quotes_n_3m", "expected_pipeline_value",
                   "conv_flow_value_12m", "realization_quote_12m", "discount_pct_12m", "gm_pct_12m"]
ML_FEATURES = ["month_in_qtr", "is_qtr_start", "trend", "seasonal_baseline",
               "regular_value_lag12_target", "n_orders_lag12_target"] + ORIGIN_FEATURES


def seasonal_baseline(y: pd.Series, origin: pd.Timestamp, target: pd.Timestamp) -> float:
    """Average of the last 4 months that sit in the same position of the quarter as `target`, known at `origin`."""
    k = [target - pd.DateOffset(months=3 * i) for i in range(1, 9)]
    known = [m for m in k if m <= origin and m in y.index and pd.notna(y.get(m))]
    return float(np.mean([y[m] for m in known[:4]])) if len(known) >= 2 else np.nan


def design_matrix(feat: pd.DataFrame, h: int, horizon_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    One row per TARGET month M, forecast from ORIGIN T = M - h (the last month with actuals).
      - calendar features describe the target month M
      - lag-12 features come from M-12 (always known because h <= 6 < 12)
      - "at origin" features come from feature row T+1, which only uses data up to T
    """
    y = feat["regular_value"]
    first = feat.index.min()
    end = horizon_end or feat.index.max()
    targets = pd.date_range(first + pd.DateOffset(months=12), end, freq="MS")
    rows = []
    for M in targets:
        T = M - pd.DateOffset(months=h)
        row_T1 = T + pd.DateOffset(months=1)
        r = {"target_month": M, "origin": T, "h": h,
             "month_in_qtr": (M.month - 1) % 3 + 1,
             "is_qtr_start": int((M.month - 1) % 3 == 0),
             "trend": (M.year - first.year) * 12 + M.month - first.month,
             "seasonal_baseline": seasonal_baseline(y, T, M),
             "regular_value_lag12_target": y.get(M - pd.DateOffset(months=12), np.nan),
             "n_orders_lag12_target": feat["n_orders"].get(M - pd.DateOffset(months=12), np.nan)}
        for c in ORIGIN_FEATURES:
            r[c] = feat[c].get(row_T1, np.nan)
        r["y_regular"] = y.get(M, np.nan)
        r["y_total"] = feat["order_value"].get(M, np.nan)
        rows.append(r)
    return pd.DataFrame(rows).set_index("target_month")


def expected_large(feat: pd.DataFrame, origin: pd.Timestamp, window: int = LARGE_WINDOW) -> float:
    """Expected large-order value per month = average of the last `window` months, known at `origin`."""
    hist = feat.loc[:origin, "large_value"].dropna()
    return float(hist.iloc[-window:].mean())


# --------------------------------------------------------------------------------------
# 4. The models (11): baseline, 3 time-series, 7 machine-learning
# --------------------------------------------------------------------------------------
# Each model answers: "given everything known at `origin`, what is regular order value in months origin+1 ... origin+H?"
# Time-series models forecast all H months from one fit. ML models use one direct model per h.

def model_seasonal_baseline(feat, origin, H, **_):
    y = feat["regular_value"]
    return [seasonal_baseline(y, origin, origin + pd.DateOffset(months=h)) for h in range(1, H + 1)]


ARIMA_ORDERS = [(p, 0, q) for p in range(3) for q in range(3) if p + q > 0]


def fit_arima(y_log):
    """Pick the ARIMA(p,0,q) with the lowest AIC (p, q in 0..2). Uses ONLY the series' own history."""
    best = None
    for order in ARIMA_ORDERS:
        try:
            fit = ARIMA(y_log, order=order, trend="c").fit()
        except Exception:
            continue
        if best is None or fit.aic < best.aic:
            best = fit
    return best


def model_arima(feat, origin, H, **_):
    y = np.log1p(feat.loc[:origin, "regular_value"].dropna())
    return list(np.expm1(fit_arima(y).forecast(H).values))


def fit_ets(y_log):
    return ExponentialSmoothing(y_log, trend="add", damped_trend=True, seasonal="add", seasonal_periods=3).fit()


def model_ets(feat, origin, H, **_):
    y = np.log1p(feat.loc[:origin, "regular_value"].dropna())
    return list(np.expm1(fit_ets(y).forecast(H).values))


def fit_sarima(y_log):
    return SARIMAX(y_log, order=(1, 0, 0), seasonal_order=(1, 0, 0, 3), trend="c").fit(disp=False)


def model_sarima(feat, origin, H, **_):
    y = np.log1p(feat.loc[:origin, "regular_value"].dropna())
    return list(np.expm1(fit_sarima(y).forecast(H).values))


# ---- machine-learning model makers (all use ML_FEATURES) ----
def make_linear():
    return make_pipeline(StandardScaler(), LinearRegression())


def make_ridge():
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 4, 30)))


def make_forest():
    return RandomForestRegressor(n_estimators=200, min_samples_leaf=3, max_features=0.5, random_state=0)


def make_boosting():
    return GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0)


def make_xgboost():
    return XGBRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                        min_child_weight=3, random_state=0, n_jobs=1, verbosity=0)


def make_lightgbm():
    # small data: few leaves, small minimum leaf size, otherwise LightGBM refuses to split
    return LGBMRegressor(n_estimators=200, num_leaves=4, max_depth=2, learning_rate=0.05, min_child_samples=5,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=0, n_jobs=1, verbose=-1)


def make_catboost():
    return CatBoostRegressor(iterations=300, depth=3, learning_rate=0.05, random_seed=0, verbose=0,
                             thread_count=1, allow_writing_files=False)


ML_MAKERS = {
    "Linear regression": make_linear,
    "Ridge": make_ridge,
    "Random forest": make_forest,
    "Gradient boosting": make_boosting,
    "XGBoost": make_xgboost,
    "LightGBM": make_lightgbm,
    "CatBoost": make_catboost,
}
TS_FITTERS = {"ARIMA": fit_arima, "ETS": fit_ets, "SARIMA": fit_sarima}   # univariate time-series models


def _ml_model(make_model):
    def predict(feat, origin, H, designs):
        preds = []
        for h in range(1, H + 1):
            X = designs[h]
            train = X[(X.index <= origin) & (X.index >= TRAIN_START)].dropna(subset=ML_FEATURES + ["y_regular"])
            model = make_model().fit(train[ML_FEATURES], train["y_regular"])
            target = origin + pd.DateOffset(months=h)
            preds.append(float(model.predict(X.loc[[target], ML_FEATURES].fillna(train[ML_FEATURES].median()))[0]))
        return preds
    return predict


MODELS = {
    "Seasonal baseline": model_seasonal_baseline,
    "ARIMA": model_arima,
    "ETS": model_ets,
    "SARIMA": model_sarima,
    **{name: _ml_model(maker) for name, maker in ML_MAKERS.items()},
}

MODEL_INFO = {
    "Seasonal baseline": ("Simple rule", "Average of the last 4 months in the same position of the quarter. The benchmark every model must beat."),
    "ARIMA": ("Time series, own history only", "ARIMA(p,0,q) on log values, order picked by lowest AIC. Uses no features and no seasonality: only the series' own past values and errors."),
    "ETS": ("Time series", "Holt-Winters exponential smoothing on log values, damped trend + 3-month (quarterly) season."),
    "SARIMA": ("Time series", "Seasonal ARIMA(1,0,0)(1,0,0)[3] on log values: last month + same month last quarter."),
    "Linear regression": ("Machine learning, linear", "Ordinary least squares on the 13 features, with no penalty. Shows what happens without shrinkage."),
    "Ridge": ("Machine learning, linear", "Linear regression with a penalty that shrinks weak features (strength chosen by cross-validation)."),
    "Random forest": ("Machine learning, trees", "Average of 200 decision trees, each on a random sample of rows/features."),
    "Gradient boosting": ("Machine learning, trees", "scikit-learn: 200 shallow trees added one after another, each correcting the previous errors."),
    "XGBoost": ("Machine learning, trees", "Regularised gradient boosting (XGBoost library), depth-2 trees, row and column sampling."),
    "LightGBM": ("Machine learning, trees", "Fast leaf-wise gradient boosting (LightGBM library), limited to 4 leaves for small data."),
    "CatBoost": ("Machine learning, trees", "Gradient boosting with symmetric trees (CatBoost library), robust to overfitting on small data."),
}


# --------------------------------------------------------------------------------------
# 5. Backtest: train fit + walk-forward test
# --------------------------------------------------------------------------------------
def run_backtest(feat: pd.DataFrame, last_actual: pd.Timestamp, progress=None) -> pd.DataFrame:
    """
    For every model, approach (H1/H3/H6) and forecast origin, forecast regular order value,
    add the expected large-order amount, and store predictions next to actuals.

    TEST : origins Dec 2024 ... (last_actual - H). Each model is refit using only data up to the origin.
    TRAIN: models fit once on Oct 2021 - Dec 2024 and scored on those same months (in-sample).
    """
    Hmax = max(APPROACHES.values())
    designs = {h: design_matrix(feat, h) for h in range(1, Hmax + 1)}
    out = []

    # ---- TEST: walk-forward, refit at every origin ----
    origins = pd.date_range(TEST_START - pd.DateOffset(months=1), last_actual - pd.DateOffset(months=1), freq="MS")
    steps, done = len(MODELS) * len(origins), 0
    for name, fn in MODELS.items():
        for T in origins:
            H = min(Hmax, (last_actual.year - T.year) * 12 + last_actual.month - T.month)
            preds = fn(feat, T, H, designs=designs)
            large = expected_large(feat, T)
            for h, p in enumerate(preds, start=1):
                M = T + pd.DateOffset(months=h)
                out.append(dict(model=name, set="test", origin=T, h=h, target_month=M, pred_regular=p,
                                pred_total=p + large, actual_regular=feat.at[M, "regular_value"],
                                actual_total=feat.at[M, "order_value"]))
            done += 1
            if progress:
                progress(done / steps, f"{name}: origin {T:%b %Y}")

    # ---- TRAIN: in-sample fit on the training period ----
    train_end = TEST_START - pd.DateOffset(months=1)
    for name, fn in MODELS.items():
        for h in range(1, Hmax + 1):
            X = designs[h]
            tr = X[(X.index >= TRAIN_START) & (X.index <= train_end)]
            if name in ML_MAKERS:
                fit_rows = tr.dropna(subset=ML_FEATURES + ["y_regular"])
                model = ML_MAKERS[name]().fit(fit_rows[ML_FEATURES], fit_rows["y_regular"])
                preds = pd.Series(model.predict(fit_rows[ML_FEATURES]), index=fit_rows.index)
            elif name == "Seasonal baseline":
                preds = tr["seasonal_baseline"]
            else:   # ARIMA / ETS / SARIMA: in-sample fitted values (one-step) on the training period
                y = np.log1p(feat.loc[:train_end, "regular_value"].dropna())
                preds = np.expm1(TS_FITTERS[name](y).fittedvalues).reindex(tr.index)
            for M, p in preds.items():
                T = M - pd.DateOffset(months=h)
                large = expected_large(feat, T)
                out.append(dict(model=name, set="train", origin=T, h=h, target_month=M, pred_regular=p,
                                pred_total=p + large, actual_regular=feat.at[M, "regular_value"],
                                actual_total=feat.at[M, "order_value"]))
    return pd.DataFrame(out)


# --------------------------------------------------------------------------------------
# 6. Scoring
# --------------------------------------------------------------------------------------
METRICS = ["MAE", "MAPE", "RMSE", "WAPE", "Bias", "R2"]


def _metrics(pred, actual):
    """
    MAE  : average absolute miss ($)
    MAPE : average of |miss| / actual (%). Months with tiny actuals blow this up, so read it with care.
    RMSE : square-root of the average squared miss ($). Punishes big misses more than MAE.
    WAPE : total |miss| / total actual (%). Like MAPE but weighted by size, so small months don't dominate.
    Bias : total (forecast - actual) / total actual (%). + = too high overall, - = too low.
    R2   : 1 - squared error / variance of actual. 1 = perfect, 0 = no better than the average, < 0 = worse.
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    err = pred - actual
    pos = actual > 0
    sst = ((actual - actual.mean()) ** 2).sum()
    return {
        "MAE": np.abs(err).mean(),
        "MAPE": (np.abs(err[pos]) / actual[pos]).mean(),
        "RMSE": np.sqrt((err ** 2).mean()),
        "WAPE": np.abs(err).sum() / actual.sum(),
        "Bias": err.sum() / actual.sum(),
        "R2": 1 - (err ** 2).sum() / sst if sst > 0 else np.nan,
    }


def _approach_rows(bt: pd.DataFrame, approach: str):
    """Train rows and test rows for one approach. Test keeps only origins whose whole window has actuals."""
    H = APPROACHES[approach]
    last_actual = bt.loc[bt["set"] == "test", "target_month"].max()
    d = bt[bt["h"] <= H]
    test = d[(d["set"] == "test") & (d["origin"] <= last_actual - pd.DateOffset(months=H))]
    train = d[d["set"] == "train"].dropna(subset=["pred_regular"])
    return train, test


def metrics_table(bt: pd.DataFrame, approach: str, target: str = "regular") -> pd.DataFrame:
    """All six metrics for every model, on train and on test. Columns: (metric, set)."""
    train, test = _approach_rows(bt, approach)
    rows = {}
    for name in MODELS:
        tr, te = train[train["model"] == name], test[test["model"] == name]
        m_tr = _metrics(tr[f"pred_{target}"], tr[f"actual_{target}"])
        m_te = _metrics(te[f"pred_{target}"], te[f"actual_{target}"])
        rows[name] = {**{(k, "Train"): v for k, v in m_tr.items()}, **{(k, "Test"): v for k, v in m_te.items()}}
    t = pd.DataFrame(rows).T
    t.columns = pd.MultiIndex.from_tuples(t.columns, names=["Metric", "Set"])
    return t[[(m, s) for m in METRICS for s in ("Train", "Test")]]


def score_table(bt: pd.DataFrame, approach: str) -> pd.DataFrame:
    """
    Comparison table for one approach. H1 uses h=1, H3 uses h=1..3, H6 uses h=1..6.
    Test only uses origins whose whole window has actuals, so every model is scored on the same months.

    Ranking uses REGULAR orders: the expected large-order amount is identical for every model, and
    total-value MAE rewards forecasts that are too low (most months have no large order).
    """
    H = APPROACHES[approach]
    train, test = _approach_rows(bt, approach)
    rows = []
    for name in MODELS:
        tr, te = train[train["model"] == name], test[test["model"] == name]
        r_tr, r_te = _metrics(tr["pred_regular"], tr["actual_regular"]), _metrics(te["pred_regular"], te["actual_regular"])
        t_te = _metrics(te["pred_total"], te["actual_total"])
        period = te.groupby("origin")[["pred_total", "actual_total"]].sum()
        rows.append({
            "Model": name,
            "Train MAE ($M)": r_tr["MAE"] / 1e6,
            "Test MAE ($M)": r_te["MAE"] / 1e6,
            "Gap (test / train)": r_te["MAE"] / r_tr["MAE"],
            "Test MAPE": r_te["MAPE"],
            "Test RMSE ($M)": r_te["RMSE"] / 1e6,
            "Test WAPE": r_te["WAPE"],
            "Test bias": r_te["Bias"],
            "Train R2": r_tr["R2"],
            "Test R2": r_te["R2"],
            "Total: test MAE ($M)": t_te["MAE"] / 1e6,
            "Total: test bias": t_te["Bias"],
            f"Total: {H}-month sum error": (period["pred_total"] - period["actual_total"]).abs().sum() / period["actual_total"].sum(),
            "Test forecasts": len(te),
        })
    t = pd.DataFrame(rows).set_index("Model")
    t["Rank"] = t["Test MAE ($M)"].rank(method="first").astype(int)
    return t.sort_values("Rank")


def summary_table(bt: pd.DataFrame) -> pd.DataFrame:
    """Test MAE on regular orders ($M) for every model x approach."""
    return pd.DataFrame({a: score_table(bt, a)["Test MAE ($M)"] for a in APPROACHES}).loc[list(MODELS)]


# --------------------------------------------------------------------------------------
# 7. Final forecast
# --------------------------------------------------------------------------------------
def final_forecast(feat: pd.DataFrame, last_actual: pd.Timestamp, bt: pd.DataFrame) -> pd.DataFrame:
    """
    Forecast from origin = last_actual with the best model (lowest test MAE) for each approach.
    The low-high range is the 10th-90th percentile of that model's test errors at the same h.
    """
    Hmax = max(APPROACHES.values())
    horizon_end = last_actual + pd.DateOffset(months=Hmax)
    designs = {h: design_matrix(feat.reindex(pd.date_range(feat.index.min(), horizon_end, freq="MS")), h)
               for h in range(1, Hmax + 1)}
    feat_ext = feat.reindex(pd.date_range(feat.index.min(), horizon_end, freq="MS"))
    large = expected_large(feat, last_actual)
    out = []
    for approach, H in APPROACHES.items():
        best = score_table(bt, approach).index[0]
        preds = MODELS[best](feat_ext, last_actual, H, designs=designs)
        test = bt[(bt["model"] == best) & (bt["set"] == "test")]
        for h, p in enumerate(preds, start=1):
            err = (test.loc[test["h"] == h, "actual_total"] - test.loc[test["h"] == h, "pred_total"])
            point = p + large
            out.append(dict(approach=approach, model=best, h=h, month=last_actual + pd.DateOffset(months=h),
                            regular=p, expected_large=large, forecast=point,
                            low=max(0.0, point + err.quantile(0.10)), high=point + err.quantile(0.90)))
    return pd.DataFrame(out)


# --------------------------------------------------------------------------------------
def run_all(path=DATA_FILE, save=True, progress=None):
    df = load_data(path)
    feat, last_actual = build_features(df)
    bt = run_backtest(feat, last_actual, progress=progress)
    fc = final_forecast(feat, last_actual, bt)
    if save:
        OUT_DIR.mkdir(exist_ok=True)
        feat.to_csv(OUT_DIR / "monthly_features.csv")
        bt.to_csv(OUT_DIR / "backtest_predictions.csv", index=False)
        fc.to_csv(OUT_DIR / "forecast_results.csv", index=False)
        for a in APPROACHES:
            score_table(bt, a).to_csv(OUT_DIR / f"scores_{a}.csv")
            metrics_table(bt, a).to_csv(OUT_DIR / f"metrics_train_test_{a}.csv")
        summary_table(bt).to_csv(OUT_DIR / "scores_summary.csv")
    return df, feat, last_actual, bt, fc


if __name__ == "__main__":
    import time
    t0 = time.time()
    _, feat, last_actual, bt, fc = run_all(progress=lambda p, msg: print(f"\r{p:5.0%} {msg:40s}", end=""))
    print(f"\nDone in {time.time() - t0:.0f}s. Last actual month: {last_actual:%b %Y}")
    for a in APPROACHES:
        print(f"\n=== {a} ===")
        print(score_table(bt, a).round(3).to_string())
    print("\n=== Summary (test MAE $M) ===")
    print(summary_table(bt).round(3).to_string())
    print("\n=== Final forecast ===")
    print(fc.round(0).to_string())
