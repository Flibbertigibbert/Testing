"""
Order Value Forecast: a guided walkthrough of the approach, from raw data to final forecast.

Run:  streamlit run app.py
Every page shows the explanation, the result, and the exact code (from forecast_pipeline.py) that produced it.
"""
import inspect
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import forecast_pipeline as fp

st.set_page_config(page_title="Order Value Forecast", page_icon="📈", layout="wide")

OUT = fp.OUT_DIR
BLUE, RED, GRAY, GREEN = "#2563eb", "#dc2626", "#9ca3af", "#16a34a"
MODEL_COLORS = dict(zip(fp.MODELS, ["#374151", "#93c5fd", "#2563eb", "#7c3aed", "#a3e635", "#059669",
                                     "#d97706", "#dc2626", "#db2777", "#0891b2", "#78350f"]))
MODEL_GROUPS = {
    "Simple rule": ["Seasonal baseline"],
    "Time series (no features)": ["ARIMA", "ETS", "SARIMA"],
    "Machine learning: linear": ["Linear regression", "Ridge"],
    "Machine learning: trees / boosting": ["Random forest", "Gradient boosting", "XGBoost", "LightGBM", "CatBoost"],
}
METRIC_HELP = {
    "MAE": "Mean Absolute Error: average miss per month, in $. Easy to read; lower is better.",
    "MAPE": "Mean Absolute Percentage Error: average miss as a % of that month's actual. Small months inflate it.",
    "RMSE": "Root Mean Squared Error: like MAE, but big misses count extra. Lower is better.",
    "WAPE": "Weighted Absolute Percentage Error: total miss ÷ total actual. Fairer than MAPE when months differ in size.",
    "Bias": "Total (forecast − actual) ÷ total actual. + means too high overall, − too low. Closest to 0 is best.",
    "R2": "R²: share of month-to-month variation explained. 1 = perfect, 0 = no better than the average, < 0 = worse than the average.",
}
METRIC_FMT = {"MAE": lambda v: f"${v / 1e6:.3f}M", "RMSE": lambda v: f"${v / 1e6:.3f}M", "MAPE": "{:.1%}",
              "WAPE": "{:.1%}", "Bias": "{:+.1%}", "R2": "{:.2f}"}


# ======================================================================================
# Data loading (cached). Uses saved outputs if present, otherwise runs the pipeline.
# ======================================================================================
@st.cache_data(show_spinner="Loading data and building features…")
def load_core():
    df = fp.load_data()
    feat, last_actual = fp.build_features(df)
    return df, feat, last_actual


@st.cache_data(show_spinner=False)
def load_results():
    files = [OUT / "backtest_predictions.csv", OUT / "forecast_results.csv"]
    if not all(f.exists() for f in files):
        return None, None
    bt = pd.read_csv(files[0], parse_dates=["origin", "target_month"])
    fc = pd.read_csv(files[1], parse_dates=["month"])
    return bt, fc


def rerun_pipeline():
    bar = st.sidebar.progress(0.0, text="Starting…")
    fp.run_all(progress=lambda p, msg: bar.progress(min(p, 1.0), text=msg))
    bar.empty()
    st.cache_data.clear()


# ======================================================================================
# Helpers
# ======================================================================================
def show_code(obj, title="Show the code", section=None, expanded=False):
    """Show the source of a function from forecast_pipeline.py, optionally only one '# ---- name' section."""
    src = inspect.getsource(obj)
    if section:
        lines = src.splitlines()
        start = next(i for i, l in enumerate(lines) if f"# ---- {section}" in l)
        end = next((i for i in range(start + 1, len(lines)) if "# ----" in lines[i]), len(lines))
        src = textwrap.dedent("\n".join(lines[start:end]))
    with st.expander(f"💻 {title}", expanded=expanded):
        st.code(src, language="python")


def money(x, digits=2):
    return f"${x / 1e6:,.{digits}f}M"


def step_header(n, title, purpose):
    st.markdown(f"### Step {n}: {title}" if n else f"### {title}")
    st.caption(purpose)


FEATURE_INFO = [
    # group, feature, meaning, months ahead available
    ("Calendar", "month_num", "Month of year (1–12)", "Any"),
    ("Calendar", "quarter", "Quarter (1–4)", "Any"),
    ("Calendar", "month_in_qtr", "Position in quarter: 1, 2 or 3", "Any"),
    ("Calendar", "is_qtr_start", "1 for Jan/Apr/Jul/Oct", "Any"),
    ("Calendar", "is_year_end", "1 for December", "Any"),
    ("Calendar", "trend", "Month counter, captures long-term growth", "Any"),
    ("Past orders", "order_value_lag1/2/3/12", "Total order value 1, 2, 3 and 12 months before", "1–12"),
    ("Past orders", "order_value_roll_mean3/6/12", "Average total order value over the previous 3/6/12 months", "1"),
    ("Past orders", "order_value_roll_median12", "Median of the previous 12 months (resistant to spikes)", "1"),
    ("Past orders", "regular_value_lag* / roll*", "Same set for orders below $1M", "1–12"),
    ("Past orders", "n_orders_lag* / roll*", "Same set for the number of orders", "1–12"),
    ("Past orders", "regular_value_same_mq_mean", "Average of the last 4 months in the same position of the quarter", "1–3"),
    ("Large orders", "large_count_roll12", "Number of orders ≥ $1M in the previous 12 months", "1"),
    ("Large orders", "large_value_roll12", "Value of orders ≥ $1M in the previous 12 months", "1"),
    ("Pipeline", "open_quotes_n_3m / _6m", "Quotes created in the last 3/6 months that have not become an order yet", "1"),
    ("Pipeline", "open_quotes_value_3m / _6m", "Net amount of those open quotes", "1"),
    ("Pipeline", "new_quotes_n_lag1 / value", "Quotes created last month (count, net amount)", "1"),
    ("Pipeline", "new_opps_n_lag1 / value", "Opportunities created last month (count, value)", "1"),
    ("Conversion", "conv_flow_n_6m / 12m", "Orders in last 6/12 months ÷ quotes created in the same period", "1"),
    ("Conversion", "conv_flow_value_6m / 12m", "Same, by value: order value ÷ quote net amount", "1"),
    ("Conversion", "conv_cohort_n", "Share of quotes created 9–20 months ago (fully settled) that converted", "1"),
    ("Conversion", "conv_cohort_value", "Same, weighted by quote value", "1"),
    ("Realization", "realization_quote_3m/6m/12m", "Order value ÷ quote net amount of quotes that converted", "1"),
    ("Realization", "realization_list_12m", "Order value ÷ list price", "1"),
    ("Realization", "realization_opp_12m", "Order value ÷ opportunity value", "1"),
    ("Discount", "discount_pct_3m/6m/12m", "Discount ÷ (order value + discount) on recent orders", "1"),
    ("Discount", "discount_value_lag1", "Discount dollars on last month's orders", "1"),
    ("Discount", "open_quotes_discount_pct_6m", "1 − net ÷ list on open quotes", "1"),
    ("Discount", "new_quotes_discount_pct_lag1", "1 − net ÷ list on quotes created last month", "1"),
    ("Gross margin", "gm_pct_3m/6m/12m", "Gross margin ÷ order value on recent orders", "1"),
    ("Gross margin", "gm_value_lag1 / roll12", "Margin dollars last month / last 12 months", "1"),
    ("Other", "avg_order_size_12m", "Average order value, last 12 months", "1"),
    ("Other", "avg_months_to_order_12m", "Average months from quote to order", "1"),
    ("Other", "expected_pipeline_value", "Open quote value × settled conversion × realization", "1"),
]


# ======================================================================================
# Pages
# ======================================================================================
def page_overview(df, feat, last_actual, bt, fc):
    st.title("📈 Order Value Forecast")
    st.markdown("#### From raw quotes to a 1-, 3- and 6-month forecast of order value")
    st.info("**Data note:** the dataset is *generated test data* (see `generate_opp_order_quote.py`). "
            "The approach and code are built to run unchanged on real data.", icon="ℹ️")

    orders = df[df["order_number"].notna()]
    c = st.columns(5)
    c[0].metric("Quotes", f"{len(df):,}")
    c[1].metric("Opportunities", f"{df['opp_id'].nunique():,}")
    c[2].metric("Orders", f"{len(orders):,}")
    c[3].metric("Months of history", f"{feat['order_value'].notna().sum()}")
    c[4].metric("Total order value", money(orders["order_value"].sum(), 1))

    st.markdown("#### The approach in 7 steps")
    steps = [
        ("1", "Data", "Quote-level CSV: one row per quote, order columns filled when it converted."),
        ("2", "Monthly series", "Sum order value per month. Split regular (< $1M) and large orders."),
        ("3", "Features", "71 monthly features, each using only information known at the start of the month."),
        ("4", "Approach", "3 horizons (H1, H3, H6), direct forecasting, walk-forward train/test."),
        ("5", "Models", "11 models: a seasonal baseline, 3 time-series (incl. ARIMA) and 7 machine-learning models (incl. XGBoost, LightGBM, CatBoost)."),
        ("6", "Results", "Compare train vs test error and pick the best model per horizon."),
        ("7", "Forecast", "Best model per horizon + expected large orders, with a low–high range."),
    ]
    cols = st.columns(7)
    for col, (n, t, d) in zip(cols, steps):
        with col:
            with st.container(border=True):
                st.markdown(f"**{n}. {t}**")
                st.caption(d)

    if bt is not None:
        st.markdown("#### Headline result")
        summary = fp.summary_table(bt)
        nxt = fc[fc["approach"] == "H1"].iloc[0]
        h6 = fc[fc["approach"] == "H6"]
        c = st.columns(3)
        c[0].metric(f"Next month ({nxt['month']:%b %Y})", money(nxt["forecast"]),
                    help=f"Range {money(nxt['low'])} – {money(nxt['high'])}")
        c[1].metric("Next 6 months total", money(h6["forecast"].sum(), 1))
        c[2].metric("Best model (all horizons)", summary.idxmin().mode()[0])
        st.caption("Use the menu on the left to walk through each step. Every page has a 💻 *Show the code* panel.")


def page_data(df, feat, last_actual, bt, fc):
    step_header(1, "The raw data", "What one row means and which columns matter.")
    st.markdown("""
Each row is **one quote**. An opportunity can have several quotes (revisions). When a quote turns into an order,
the order columns (`order_number`, `order_date_month`, `order_value`, `discount_amount`, `gross_margin`) are filled in.
""")
    st.dataframe(df.head(20), width="stretch", height=300)

    st.markdown("#### Checks I ran before modelling")
    orders = df[df["order_number"].notna()].copy()
    lag = ((orders["order_date_month"].dt.year - orders["quote_creation_date"].dt.year) * 12
           + orders["order_date_month"].dt.month - orders["quote_creation_date"].dt.month)
    c = st.columns(4)
    c[0].metric("Orders appear once", "Yes" if orders["order_number"].is_unique else "No")
    c[1].metric("Months quote → order", f"median {lag.median():.0f}, max {lag.max():.0f}")
    c[2].metric("Order ÷ quote net", f"{(orders['order_value'] / orders['quote_net_amount']).median():.0%} (median)")
    c[3].metric("Orders after quote expiry", f"{(orders['order_date_month'] > orders['quote_expiry_date']).sum()}")

    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(lag, nbins=9, title="Months from quote to order", labels={"value": "months"})
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, width="stretch")
    with col2:
        fig = px.histogram(orders["order_value"] / orders["quote_net_amount"], nbins=30,
                           title="Order value ÷ quote net amount (realization)")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, width="stretch")
    st.markdown("""
**What this tells us**
- Orders arrive **0–8 months** after the quote → a quote is only "settled" after ~9 months (used for conversion features).
- Orders are worth **70–110 %** of the quote net amount → the open pipeline is informative.
- Many orders arrive **after** the quote's expiry date → expiry is *not* used to decide if a quote is still open.
- `quote_status` is the quote's *current* status, not known at the time → **excluded** (it would leak the future).
""")
    show_code(fp.load_data)


def page_series(df, feat, last_actual, bt, fc):
    step_header(2, "The monthly order-value series", "Turn orders into one number per month: the thing we forecast.")
    hist = feat.loc[:last_actual]
    fig = go.Figure()
    fig.add_bar(x=hist.index, y=hist["regular_value"] / 1e6, name="Regular orders (< $1M)", marker_color=BLUE)
    fig.add_bar(x=hist.index, y=hist["large_value"] / 1e6, name="Large orders (≥ $1M)", marker_color=RED)
    fig.update_layout(barmode="stack", title="Monthly order value", yaxis_title="$M", height=380, legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    orders = df[df["order_number"].notna()]
    large_share = orders.loc[orders["order_value"] >= fp.LARGE, "order_value"].sum() / orders["order_value"].sum()
    mq = hist.groupby("month_in_qtr")[["regular_value", "n_orders"]].mean()

    col1, col2 = st.columns([1, 1])
    with col1:
        fig = px.bar(x=["1st month (Jan/Apr/Jul/Oct)", "2nd month", "3rd month"], y=mq["regular_value"] / 1e6,
                     title="Quarterly rhythm: average regular order value", labels={"x": "", "y": "$M"},
                     color_discrete_sequence=[BLUE])
        fig.update_layout(height=320)
        st.plotly_chart(fig, width="stretch")
    with col2:
        st.markdown("#### Two patterns drive everything")
        st.markdown(f"""
1. **Quarterly rhythm:** the first month of every quarter is much bigger than the other two.
   This is the main thing a model can learn.
2. **Large orders are lumpy:** {(orders['order_value'] >= fp.LARGE).sum()} orders of $1M or more make up
   **{large_share:.0%}** of all value, at unpredictable times.

➡️ So I forecast **regular orders** with models, and add **large orders** as an expected monthly amount
(their {fp.LARGE_WINDOW}-month average).
""")
    with st.expander("Largest orders"):
        st.dataframe(orders.nlargest(10, "order_value")[["order_date_month", "order_value", "global_entity"]],
                     width="stretch", hide_index=True)
    show_code(fp.build_features, "Show the code: monthly targets", section="targets")


def page_features(df, feat, last_actual, bt, fc):
    step_header(3, "Feature creation", "71 monthly features. Every one uses only information known at the start of the month.")
    st.markdown("""
#### The rule that keeps the forecast honest
Row **M** may only use data from **before month M starts**. In code that means `shift(1)` for past values,
and date windows that end *before* M. Without this rule the backtest would look great and fail in real use.
""")
    info = pd.DataFrame(FEATURE_INFO, columns=["Group", "Feature", "Meaning", "Months ahead available"])
    groups = ["All"] + list(dict.fromkeys(info["Group"]))
    g = st.radio("Feature group", groups, horizontal=True)
    st.dataframe(info if g == "All" else info[info["Group"] == g], width="stretch", hide_index=True)

    st.markdown("#### Which features move with regular order value?")
    hist = feat.loc[:last_actual]
    cols = [c for c in feat.columns if c not in fp.TARGET_COLS]
    corr = hist[cols].corrwith(hist["regular_value"], method="spearman").dropna()
    top = corr.reindex(corr.abs().sort_values(ascending=False).index).head(15)[::-1]
    col1, col2 = st.columns([1, 1])
    with col1:
        fig = px.bar(x=top.values, y=top.index, orientation="h", title="Top 15 (Spearman correlation)",
                     color=top.values > 0, color_discrete_map={True: BLUE, False: RED}, labels={"x": "correlation", "y": ""})
        fig.update_layout(showlegend=False, height=460)
        st.plotly_chart(fig, width="stretch")
    with col2:
        pick = st.selectbox("Plot a feature against regular order value", cols,
                            index=cols.index("open_quotes_n_3m"))
        fig = go.Figure()
        fig.add_bar(x=hist.index, y=hist["regular_value"] / 1e6, name="Regular order value ($M)", marker_color=GRAY)
        fig.add_scatter(x=hist.index, y=hist[pick], name=pick, yaxis="y2", line=dict(color=BLUE))
        fig.update_layout(height=400, yaxis=dict(title="$M"), yaxis2=dict(overlaying="y", side="right", title=pick),
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Correlation with regular order value: **{corr.get(pick, np.nan):.2f}**. "
                   "With ~60 months, values below ~0.25 cannot be told apart from chance.")

    st.markdown("#### The code, by feature group")
    tabs = st.tabs(["Calendar", "Past orders", "Pipeline", "Conversion / realization / discount / margin"])
    for tab, sec in zip(tabs, ["calendar", "past orders", "pipeline", "conversion"]):
        with tab:
            src = inspect.getsource(fp.build_features).splitlines()
            s = next(i for i, l in enumerate(src) if f"# ---- {sec}" in l)
            e = next((i for i in range(s + 1, len(src)) if "# ----" in src[i]), len(src))
            st.code(textwrap.dedent("\n".join(src[s:e])), language="python")


def page_approach(df, feat, last_actual, bt, fc):
    step_header(4, "Forecast approach", "Three horizons, direct forecasting, and an honest train/test split.")
    st.markdown("#### Three forecast approaches")
    c = st.columns(3)
    for col, (a, H) in zip(c, fp.APPROACHES.items()):
        with col:
            with st.container(border=True):
                st.markdown(f"**{a}: next {H} month{'s' if H > 1 else ''}**")
                st.caption(f"Made at the end of month T, forecasts T+1{f' … T+{H}' if H > 1 else ''}. "
                           f"From Oct 2026: {(last_actual + pd.DateOffset(months=1)):%b %Y}"
                           f"{f' – {(last_actual + pd.DateOffset(months=H)):%b %Y}' if H > 1 else ''}.")

    st.markdown("""
#### Direct forecasting: one model per step ahead
For the ML models I train a **separate model for each h = 1…6**. The model for h=3 learns
*"given what I knew 3 months earlier, what happened?"*. Each training row pairs:
- **calendar of the target month** (always known),
- **the target month's value a year earlier** (known, because h ≤ 6 < 12),
- **pipeline and ratio features from the forecast origin T**, i.e. data up to T only.

Time-series models (ETS, SARIMA) forecast all H months from one fit. The baseline uses the
same-quarter-position months that are already known.
""")

    st.markdown("#### Train vs test (walk-forward)")
    first_test, train_start = fp.TEST_START, fp.TRAIN_START
    fig = go.Figure()
    fig.add_vrect(x0=train_start, x1=first_test - pd.DateOffset(days=1), fillcolor=BLUE, opacity=0.15, line_width=0,
                  annotation_text="TRAIN (fit + in-sample score)", annotation_position="top left")
    fig.add_vrect(x0=first_test, x1=last_actual + pd.DateOffset(days=27), fillcolor=GREEN, opacity=0.15, line_width=0,
                  annotation_text="TEST (walk-forward)", annotation_position="top left")
    hist = feat.loc[:last_actual]
    fig.add_bar(x=hist.index, y=hist["regular_value"] / 1e6, marker_color=GRAY, name="Regular order value")
    fig.update_layout(height=320, yaxis_title="$M", showlegend=False)
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"""
- **Train ({train_start:%b %Y} – {(first_test - pd.DateOffset(months=1)):%b %Y}):** fit once, then score on the same months.
  This shows how well a model fits data it has *seen*.
- **Test ({first_test:%b %Y} – {last_actual:%b %Y}):** for every forecast origin T, refit using **only data up to T**,
  forecast T+1…T+H, and compare with what actually happened. This is how it would perform in real use.
- If **test error ≫ train error**, the model memorised the past (**overfitting**).
""")

    st.markdown("#### See the design matrix for one horizon")
    h = st.slider("Months ahead (h)", 1, 6, 1)
    X = fp.design_matrix(feat, h).loc[fp.TRAIN_START:last_actual]
    st.dataframe(X.tail(12).style.format(precision=2), width="stretch")
    show_code(fp.design_matrix, "Show the code: design_matrix")
    show_code(fp.seasonal_baseline, "Show the code: seasonal_baseline")
    show_code(fp.expected_large, "Show the code: expected_large")
    show_code(fp.run_backtest, "Show the code: run_backtest (train + walk-forward test)")


def page_models(df, feat, last_actual, bt, fc):
    step_header(5, "The eleven models", "From a simple rule to machine learning. All forecast regular orders; large orders are added equally.")
    code_for = {
        "Seasonal baseline": [fp.model_seasonal_baseline],
        "ARIMA": [fp.fit_arima, fp.model_arima],
        "ETS": [fp.fit_ets, fp.model_ets],
        "SARIMA": [fp.fit_sarima, fp.model_sarima],
        "Linear regression": [fp.make_linear, fp._ml_model],
        "Ridge": [fp.make_ridge, fp._ml_model],
        "Random forest": [fp.make_forest, fp._ml_model],
        "Gradient boosting": [fp.make_boosting, fp._ml_model],
        "XGBoost": [fp.make_xgboost, fp._ml_model],
        "LightGBM": [fp.make_lightgbm, fp._ml_model],
        "CatBoost": [fp.make_catboost, fp._ml_model],
    }
    for group, names in MODEL_GROUPS.items():
        st.markdown(f"#### {group}")
        if group.startswith("Time series"):
            st.caption("These use **only the past values of regular order value**: no pipeline, ratio or calendar features. "
                       "ARIMA has no seasonal part at all; ETS and SARIMA add the 3-month quarterly season.")
        for i in range(0, len(names), 3):
            cols = st.columns(3)
            for col, name in zip(cols, names[i:i + 3]):
                kind, desc = fp.MODEL_INFO[name]
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{name}**")
                        st.caption(kind)
                        st.write(desc)
                        with st.popover("💻 Code"):
                            for f in code_for[name]:
                                st.code(inspect.getsource(f), language="python")
    st.markdown("#### Features used by the seven machine-learning models")
    used = fp.active_features(fp.design_matrix(feat, 1))
    st.write(", ".join(f"`{c}`" for c in used))
    dropped = feat.attrs.get("dropped_features", {})
    if dropped:
        st.caption("Dropped because they are blank in most months: "
                   + ", ".join(f"`{c}` ({v:.0%} blank)" for c, v in dropped.items()))
    st.caption(f"I kept this to {len(used)} features on purpose: with ~40–60 training months, using all the features made the models worse.")


def page_results(df, feat, last_actual, bt, fc):
    step_header(6, "Results: comparing the eleven models", "Train vs test performance for each approach, ranked on the test set.")
    if bt is None:
        st.warning("No results yet. Click **Re-run pipeline** in the sidebar.")
        return
    approach = st.radio("Approach", list(fp.APPROACHES), horizontal=True,
                        format_func=lambda a: f"{a}: next {fp.APPROACHES[a]} month{'s' if fp.APPROACHES[a] > 1 else ''}")
    t = fp.score_table(bt, approach)
    sum_col = [c for c in t.columns if "sum error" in c][0]

    st.markdown("#### Comparison table (regular orders, ranked by test MAE)")
    fmt = {"Train MAE ($M)": "{:.3f}", "Test MAE ($M)": "{:.3f}", "Gap (test / train)": "{:.2f}×",
           "Test MAPE": "{:.1%}", "Test RMSE ($M)": "{:.3f}", "Test WAPE": "{:.1%}", "Test bias": "{:+.1%}",
           "Train R2": "{:.2f}", "Test R2": "{:.2f}",
           "Total: test MAE ($M)": "{:.3f}", "Total: test bias": "{:+.1%}", sum_col: "{:.1%}"}
    styled = (t.style.format(fmt)
              .highlight_min(subset=["Test MAE ($M)", "Test RMSE ($M)", "Test WAPE", "Test MAPE"], color="#bbf7d0")
              .highlight_max(subset=["Test R2"], color="#bbf7d0")
              .map(lambda v: "color:#dc2626;font-weight:600" if v > 1.5 else "", subset=["Gap (test / train)"]))
    st.dataframe(styled, width="stretch")
    with st.expander("How to read this table"):
        st.markdown("\n".join(f"- **{k}:** {v}" for k, v in METRIC_HELP.items()) + f"""
- **Gap (test / train):** test MAE ÷ train MAE. **Red (> 1.5×) = overfitting**: the model memorised the training months.
- **Total: …** the same after adding the expected large-order amount, i.e. on **total order value**.
  Large orders are random and identical for every model, so they don't change the ranking.
- **{sum_col}:** error on the sum over the {fp.APPROACHES[approach]} month(s), which is what matters for planning.
- **Why rank on regular orders?** A model that always forecasts too low wins on total MAE, because most months have no large order.
- **Why is test R² near or below 0?** Regular order value swings a lot from month to month; even the best model explains
  little of that swing. A high *train* R² with a negative *test* R² is the clearest sign of overfitting.
""")

    st.markdown("#### Train vs test: all six metrics")
    mt = fp.metrics_table(bt, approach)
    st.dataframe(mt.style.format({c: METRIC_FMT[c[0]] for c in mt.columns}), width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        metric = st.selectbox("Metric for the chart", fp.METRICS, help="Pick any metric to compare train and test")
        long = mt[metric].reset_index(names="Model").melt("Model", var_name="Set", value_name=metric)
        if metric in ("MAE", "RMSE"):
            long[metric] = long[metric] / 1e6
        fig = px.bar(long, x="Model", y=metric, color="Set", barmode="group",
                     title=f"Train vs test {metric}{' ($M)' if metric in ('MAE', 'RMSE') else ''}",
                     color_discrete_map={"Train": BLUE, "Test": GREEN})
        fig.update_layout(height=400, legend=dict(orientation="h", y=-0.35))
        st.plotly_chart(fig, width="stretch")
        st.caption(METRIC_HELP[metric])
    with col2:
        te = bt[(bt["set"] == "test") & (bt["origin"] <= last_actual - pd.DateOffset(months=6))]
        by_h = te.assign(err=(te["pred_regular"] - te["actual_regular"]).abs()).groupby(["model", "h"])["err"].mean().reset_index()
        fig = px.line(by_h, x="h", y=by_h["err"] / 1e6, color="model", markers=True, color_discrete_map=MODEL_COLORS,
                      title="Test error by months ahead (same target months)", labels={"y": "MAE ($M)", "h": "months ahead"})
        fig.update_layout(height=380, legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Summary: test MAE on regular orders ($M)")
    summary = fp.summary_table(bt)
    st.dataframe(summary.style.format("{:.3f}").highlight_min(axis=0, color="#bbf7d0"), width="stretch")

    st.markdown("#### Actual vs forecast (test months)")
    c1, c2 = st.columns([2, 1])
    picks = c1.multiselect("Models", list(fp.MODELS), default=[t.index[0], "ARIMA", "XGBoost"])
    h = c2.selectbox("Months ahead", range(1, fp.APPROACHES[approach] + 1))
    d = bt[(bt["set"] == "test") & (bt["h"] == h)]
    actual = d.drop_duplicates("target_month").set_index("target_month")["actual_regular"]
    fig = go.Figure()
    fig.add_bar(x=actual.index, y=actual / 1e6, name="Actual", marker_color=GRAY)
    for m in picks:
        s = d[d["model"] == m].set_index("target_month")["pred_regular"]
        fig.add_scatter(x=s.index, y=s / 1e6, name=m, mode="lines+markers", line=dict(color=MODEL_COLORS[m]))
    fig.update_layout(height=380, yaxis_title="Regular order value ($M)", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    best = summary.idxmin()
    over = t.index[t["Gap (test / train)"] > 1.5].tolist()
    st.markdown("#### Takeaways")
    st.markdown(f"""
- **Best model:** {', '.join(f'{a} → **{m}**' for a, m in best.items())}.
- **Overfitting:** {', '.join(f'**{m}**' for m in over) if over else 'none'} score much better on train than on test.
  With ~40 training months, flexible tree / boosting models (incl. XGBoost, LightGBM, CatBoost) learn noise.
- **ARIMA** (own history, no seasonality) does worse than ETS/SARIMA: without the quarterly season it misses the main pattern.
- **Linear regression** without a penalty gets worse the further ahead it forecasts; **Ridge**'s shrinkage fixes most of that.
- The simple seasonal rule is hard to beat: most of what is predictable is the **quarterly rhythm**.
- On this generated data, discount and gross margin are random by construction, so they can't help. On real data they may.
""")
    show_code(fp.score_table, "Show the code: score_table")


def page_forecast(df, feat, last_actual, bt, fc):
    step_header(7, "Final forecast", "Best model per approach + expected large orders, with a 10th–90th percentile range.")
    if fc is None:
        st.warning("No results yet. Click **Re-run pipeline** in the sidebar.")
        return
    approach = st.radio("Approach", list(fp.APPROACHES), horizontal=True, index=2,
                        format_func=lambda a: f"{a}: next {fp.APPROACHES[a]} month{'s' if fp.APPROACHES[a] > 1 else ''}")
    g = fc[fc["approach"] == approach]
    c = st.columns(4)
    c[0].metric("Model used", g["model"].iloc[0])
    c[1].metric(f"Total, next {len(g)} month{'s' if len(g) > 1 else ''}", money(g["forecast"].sum(), 1))
    c[2].metric("Regular orders", money(g["regular"].sum(), 1))
    c[3].metric("Expected large orders", money(g["expected_large"].sum(), 1))

    hist = feat.loc[last_actual - pd.DateOffset(months=23):last_actual]
    fig = go.Figure()
    fig.add_bar(x=hist.index, y=hist["order_value"] / 1e6, name="Actual", marker_color=GRAY)
    fig.add_scatter(x=list(g["month"]) + list(g["month"][::-1]), y=list(g["high"] / 1e6) + list(g["low"][::-1] / 1e6),
                    fill="toself", fillcolor="rgba(220,38,38,0.15)", line=dict(width=0), name="10–90% range")
    fig.add_scatter(x=g["month"], y=g["forecast"] / 1e6, mode="lines+markers", name="Forecast", line=dict(color=RED, width=3))
    fig.add_scatter(x=g["month"], y=g["regular"] / 1e6, mode="lines+markers", name="Regular part",
                    line=dict(color=BLUE, dash="dot"))
    fig.update_layout(height=420, yaxis_title="Order value ($M)", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    show = g[["month", "regular", "expected_large", "forecast", "low", "high"]].copy()
    show["month"] = show["month"].dt.strftime("%b %Y")
    st.dataframe(show.set_index("month").style.format(lambda v: money(v)), width="stretch")
    st.download_button("⬇️ Download all forecasts (CSV)", fc.to_csv(index=False), "forecast_results.csv", "text/csv")
    st.markdown(f"""
#### How to read it
- **Forecast = regular part (model) + expected large orders** ({money(g['expected_large'].iloc[0])} per month,
  the average of the last {fp.LARGE_WINDOW} months).
- **Range:** the 10th–90th percentile of the model's test errors at the same months ahead.
  In 8 out of 10 past months the actual fell inside a range this wide.
- The range is wide because **one large order can double a month**. Totals over several months are more reliable than any single month.
""")
    show_code(fp.final_forecast, "Show the code: final_forecast")


# ======================================================================================
# Layout
# ======================================================================================
PAGES = {
    "🏠 Overview": page_overview,
    "1 · Data": page_data,
    "2 · Monthly series": page_series,
    "3 · Features": page_features,
    "4 · Forecast approach": page_approach,
    "5 · Models": page_models,
    "6 · Results": page_results,
    "7 · Final forecast": page_forecast,
}

st.sidebar.title("Order Value Forecast")
choice = st.sidebar.radio("Walkthrough", list(PAGES), label_visibility="collapsed")
st.sidebar.divider()
if st.sidebar.button("🔄 Re-run pipeline", help="Rebuild features, backtest and forecast from the CSV (~1 minute)"):
    rerun_pipeline()
st.sidebar.caption(f"Code: `forecast_pipeline.py` · Data: `{fp.DATA_FILE.name}`")

df, feat, last_actual = load_core()
bt, fc = load_results()
if bt is None and choice in ("🏠 Overview", "6 · Results", "7 · Final forecast"):
    st.sidebar.warning("Results not built yet. Click Re-run pipeline.")
PAGES[choice](df, feat, last_actual, bt, fc)
