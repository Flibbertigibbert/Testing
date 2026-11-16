# Testing
Testing my skills on different subjests


orders = df[df["order_number"].notna()].drop_duplicates("order_number")
LAST_ACTUAL = orders["order_date_month"].max()
MONTHS = pd.date_range("2020-01-01", LAST_ACTUAL + pd.DateOffset(months=2), freq="MS")



# --- sanity check: which features move with order value, and how many months are complete? ---
target_cols  = ["order_value", "n_orders", "regular_value", "large_value", "log_order_value"]
feature_cols = [c for c in feat.columns if c not in target_cols]
hist = feat.loc[:LAST_ACTUAL]

# How many months does each feature actually have a value for?
valid = hist[feature_cols].notna().sum().sort_values()
print(f"{len(hist)} months in history. Features with the fewest filled months:")
print(valid.head(8).to_string(), "\n")

empty = valid.index[valid == 0].tolist()
if empty:
    print("No values at all, dropped:", empty, "\n")
    feature_cols = [c for c in feature_cols if c not in empty]

corr = (hist[feature_cols].corrwith(hist["regular_value"], method="spearman")
            .dropna().sort_values(key=abs, ascending=False))
print("Spearman correlation with regular (non-large) monthly order value:")
print(corr.round(2).head(15).to_string())

model_rows = hist.dropna(subset=feature_cols)
print()
if model_rows.empty:
    print("No month has every feature filled. Most-missing features:")
    print(hist[feature_cols].isna().sum().sort_values(ascending=False).head(8).to_string())
else:
    print(f"{len(feature_cols)} features | {len(model_rows)} complete months for modelling "
          f"({model_rows.index.min():%b %Y} to {model_rows.index.max():%b %Y})")
