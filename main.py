import yfinance as yf
import pandas as pd
import streamlit as st

# --- Streamlit Config ---
st.set_page_config(page_title="Stock Signal Scanner", page_icon="📈", layout="wide")

st.title("📈 Stock Signal Scanner (EMA9 / EMA20 + Volume Confirmation)")
st.markdown(
    """
Upload an Excel or CSV file with tickers in **column A**  
(e.g. RELIANCE, TCS, HDFCBANK, IOC, etc.)
"""
)

# --- Custom Styling ---
st.markdown(
    """
<style>
[data-testid="stCheckbox"] label {
    font-weight: 600;
    font-size: 0.95rem;
    color: #e2e8f0;
}
[data-testid="stCheckbox"] input:checked + div:before {
    background-color: #22c55e !important;
    border-color: #22c55e !important;
}
[data-testid="stCheckbox"] input:hover + div:before,
[data-testid="stCheckbox"] input:focus + div:before {
    border-color: #38bdf8 !important;
}
[data-testid="stCheckbox"] div[role="checkbox"] {
    transform: scale(1.1);
    margin-right: 0.3rem;
}
/* Compact Mode grid styling */
.compact-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 0.3rem 0.6rem;
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #1e293b;
    border-radius: 0.5rem;
    padding: 0.5rem;
    background: #0f172a;
}
/* Mobile-friendly column stacking */
@media (max-width: 768px) {
    [data-testid="column"] {
        width: 100% !important;
        flex-direction: column !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# --- Volume formatting helper ---
def format_volume(vol):
    try:
        vol = float(vol)
    except Exception:
        return str(vol)
    if vol >= 1e7:
        return f"{vol / 1e7:.2f} Cr"
    elif vol >= 1e5:
        return f"{vol / 1e5:.2f} L"
    else:
        return f"{vol:,.0f}"


# --- File Upload ---
file = st.file_uploader("Upload Excel or CSV file", type=["xlsx", "csv"])

if file:
    # Read tickers
    df = pd.read_excel(file) if file.name.endswith(".xlsx") else pd.read_csv(file)
    tickers = (
        df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().unique().tolist()
    )

    if len(tickers) == 0:
        st.error("No tickers found in the uploaded file.")
    else:
        st.success(f"Loaded {len(tickers)} tickers from file")

        # --- Responsive Layout ---
        left_col, right_col = st.columns([1, 2])

        with left_col:
            st.subheader("📂 Stock Selection")

            select_all = st.checkbox("✅ Select All", value=True)
            compact_mode = st.toggle("🧩 Compact Mode", value=False)
            selected = []

            with st.expander("Show / Hide Ticker List", expanded=True):
                st.caption("Check or uncheck tickers to include in the scan.")
                if select_all:
                    selected = tickers
                    if compact_mode:
                        st.markdown(
                            '<div class="compact-grid">'
                            + "".join(
                                [
                                    f"<label><input type='checkbox' checked disabled> {t}</label>"
                                    for t in tickers
                                ]
                            )
                            + "</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        for t in tickers:
                            st.checkbox(t, value=True, disabled=True, key=f"chk_{t}")
                else:
                    if compact_mode:
                        # Grid view
                        st.markdown(
                            '<div class="compact-grid">', unsafe_allow_html=True
                        )
                        cols = st.columns(4)
                        for idx, t in enumerate(tickers):
                            checked = st.checkbox(t, key=f"chk_{t}")
                            if checked:
                                selected.append(t)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        # Standard vertical list
                        for t in tickers:
                            if st.checkbox(t, value=False, key=f"chk_{t}"):
                                selected.append(t)

            st.markdown(f"**{len(selected)} selected.**")
            run_scan = st.button("▶️ Run Scan")

        with right_col:
            # --- Results Section ---
            if len(tickers) > 0 and "results" not in st.session_state:
                st.session_state.results_df = pd.DataFrame()

            if run_scan and len(selected) > 0:
                results = []
                progress = st.progress(0)

                for i, sym in enumerate(selected):
                    progress.progress((i + 1) / len(selected))
                    try:
                        # Try NSE, then BSE
                        data = yf.download(
                            f"{sym}.NS", period="6mo", interval="1d", progress=False
                        )
                        if data.empty:
                            data = yf.download(
                                f"{sym}.BO", period="6mo", interval="1d", progress=False
                            )

                        if data.empty:
                            results.append(
                                {
                                    "Ticker": sym,
                                    "Signal": "NO DATA",
                                    "Reason": "Not found",
                                }
                            )
                            continue

                        # --- Indicators ---
                        data["EMA9"] = data["Close"].ewm(span=9, adjust=False).mean()
                        data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
                        data["VolEMA14"] = (
                            data["Volume"].ewm(span=14, adjust=False).mean()
                        )

                        ema9 = data["EMA9"].values
                        ema20 = data["EMA20"].values
                        vol = data["Volume"].values
                        vol_ema = data["VolEMA14"].values

                        last_signal = None
                        cross_index = None

                        # --- Find Most Recent Crossover ---
                        for j in range(len(data) - 1, 0, -1):
                            if ema9[j] > ema20[j] and ema9[j - 1] < ema20[j - 1]:
                                last_signal = "BUY"
                                cross_index = j
                                break
                            elif ema9[j] < ema20[j] and ema9[j - 1] > ema20[j - 1]:
                                last_signal = "SELL"
                                cross_index = j
                                break

                        # --- Evaluate Crossover ---
                        if last_signal:
                            vol_cross = float(vol[cross_index])
                            vol_avg_cross = float(vol_ema[cross_index])
                            confirmed = vol_cross > vol_avg_cross

                            signal = (
                                f"CONFIRMED {last_signal}"
                                if confirmed
                                else f"WEAK {last_signal}"
                            )
                            reason = (
                                f"Most recent crossover ({last_signal}) on {data.index[cross_index].date()} "
                                f"with volume {'above' if confirmed else 'below'} avg "
                                f"({format_volume(vol_cross)} vs {format_volume(vol_avg_cross)})"
                            )

                            if (len(data) - cross_index) > 60:
                                signal = "NO SIGNAL"
                                reason = "No crossover in last 60 days"
                        else:
                            signal, reason = "NO SIGNAL", "No EMA crossover found"

                        results.append(
                            {
                                "Ticker": sym,
                                "Signal": signal,
                                "EMA9": round(float(data["EMA9"].iloc[-1]), 2),
                                "EMA20": round(float(data["EMA20"].iloc[-1]), 2),
                                "Vol Today": format_volume(data["Volume"].iloc[-1]),
                                "Vol EMA(14)": format_volume(data["VolEMA14"].iloc[-1]),
                                "Reason": reason,
                            }
                        )

                    except Exception as e:
                        results.append(
                            {"Ticker": sym, "Signal": "ERROR", "Reason": str(e)}
                        )

                results_df = pd.DataFrame(results)
                st.session_state.results_df = results_df
                st.success("Scan completed successfully ✅")

            # --- Display Results ---
            if not st.session_state.get("results_df", pd.DataFrame()).empty:
                results_df = st.session_state.results_df

                def highlight_signal(val):
                    color = (
                        "#4ade80"
                        if "BUY" in val
                        else "#f87171" if "SELL" in val else "#94a3b8"
                    )
                    return f"background-color: {color}; color: black; font-weight: 600"

                st.subheader("📊 Scan Results")
                st.dataframe(
                    results_df.style.applymap(highlight_signal, subset=["Signal"]),
                    use_container_width=True,
                )

                csv = results_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Download Results as CSV",
                    data=csv,
                    file_name="signals.csv",
                    mime="text/csv",
                )

else:
    st.info("Upload a file to begin scanning.")
