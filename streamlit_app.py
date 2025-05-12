import random
import time
import plotly.graph_objects as go
import pyotp
from NorenRestApiPy.NorenApi import NorenApi
import streamlit as st
import pandas as pd
try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

import threading
from streamlit_autorefresh import st_autorefresh

from operations import updateExcel, getTotalStraddlePrice

# === STEP 1: User credentials and keys ===
user_id = st.secrets["user"]["user_id"]
password = st.secrets["user"]["password"]
totp_secret = st.secrets["user"]["totp_secret"]
vendor_code = st.secrets["user"]["vendor_code"]
api_key = st.secrets["user"]["api_key"]
imei = st.secrets["user"]["imei"]

# === STEP 2: Generate TOTP ===
totp = pyotp.TOTP(totp_secret).now()


class ShoonyaApiPy(NorenApi):
    def __init__(self):
        NorenApi.__init__(self, host='https://api.shoonya.com/NorenWClientTP/',
                          websocket='wss://api.shoonya.com/NorenWSTP')


api = ShoonyaApiPy()

response = api.login(user_id, password, totp, vendor_code, api_key, imei)

# --- Streamlit Config ---
st.set_page_config(page_title="NIFTY Straddle Tracker", layout="wide")
st.title("📈 NIFTY ATM Straddle Premium - Live Dashboard")

# --- Session State ---
if "monitoring" not in st.session_state:
    st.session_state.monitoring = False
if "data" not in st.session_state:
    st.session_state.data = []
if "graph_data" not in st.session_state:
    st.session_state.graph_data = {"Time": [], "Total Premium": []}
if "last_10_totals" not in st.session_state:
    st.session_state.last_10_totals = []
if "message_shown" not in st.session_state:
    st.session_state.message_shown = False
if "last_logs_count" not in st.session_state:
    st.session_state.last_logs_count = 10  # Default value

# --- Add Execute Button ---
if st.button("📝 Execute"):
    if st.session_state.data:
        # Get the latest row of data
        latest_data = st.session_state.data[-1]

        # Create a DataFrame for the latest data
        df = pd.DataFrame([latest_data])

        # Write to Excel (append if file exists)
        file_name = "executed_data.xlsx"
        try:
            with pd.ExcelWriter(file_name, mode='a', if_sheet_exists='overlay') as writer:
                df.to_excel(writer, index=False, header=writer.sheets.get('Sheet1') is None, startrow=writer.sheets['Sheet1'].max_row if 'Sheet1' in writer.sheets else 0)
            st.success(f"✅ Data written to '{file_name}'")
        except Exception as e:
            st.error(f"❌ Failed to write to Excel: {e}")
    else:
        st.warning("⚠️ No data available to write!")

# --- Controls ---
col1, col2 = st.columns(2)
with col1:
    # Add a title for the "Last Logs Count" text box
    st.markdown("### Enter Last Logs Count:")
    st.session_state.last_logs_count = st.number_input(
        "Last Logs Count:",
        min_value=1,
        max_value=500,
        value=10,  # Default value
        step=1
    )
    if st.button("▶️ Start Monitoring"):
        st.session_state.monitoring = True
with col2:
    # Add a title for the "Enter % Increase" text box
    st.markdown("### Enter % Increase:")
    st.session_state.percentage_increase = st.number_input(
        "Enter % Increase:",
        min_value=0.1,
        max_value=100.0,
        value=1.0,  # Default value
        step=0.1
    )
    if st.button("⏹ Stop Monitoring"):
        st.session_state.monitoring = False

# Add a row with two columns for "Set Time Delay" and "Max Logs in Chart"
col1, col2 = st.columns(2)

with col1:
    st.markdown("### Set Time Delay (seconds):")
    st.session_state.time_delay = st.number_input(
        "Time Delay:",
        min_value=0.1,
        max_value=60.0,
        value=1.0,  # Default value
        step=0.1,
        label_visibility="collapsed"  # Hides the label to make the box smaller
    )

with col2:
    st.markdown("### Max Logs in Chart:")
    st.session_state.max_logs = st.number_input(
        "Max Logs in Chart:",
        min_value=10,
        max_value=500,
        value=100,  # Default value
        step=10,
        label_visibility="collapsed"  # Hides the label to make the box smaller
    )

# Add a toggle button for sound
st.session_state.sound_enabled = st.checkbox("Enable Sound", value=True)

st.markdown(f"**Monitoring Status:** {'🟢 ON' if st.session_state.monitoring else '🔴 OFF'}")

# --- Placeholders ---
status_placeholder = st.empty()
graph_placeholder = st.empty()
table_placeholder = st.empty()


# --- Track Alert Points ---
if "alert_points" not in st.session_state:
    st.session_state.alert_points = {"Time": [], "Total Premium": []}


# --- Function to draw chart and table ---
def update_display():
    if not st.session_state.graph_data["Time"]:
        return  # No data yet

    # Limit graph data to the last max_logs
    max_logs = st.session_state.max_logs
    time_data = st.session_state.graph_data["Time"][-max_logs:]
    premium_data = st.session_state.graph_data["Total Premium"][-max_logs:]

    # Calculate average based on the last log count
    last_logs_count = st.session_state.last_logs_count
    avg_last_logs = sum(premium_data[-last_logs_count:]) / len(premium_data[-last_logs_count:])

    # Get the latest Total Premium
    latest_total = premium_data[-1]

    fig = go.Figure()

    # Latest Total Premium (left side of center)
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.35,
        y=1.12,
        text=f"📊 Latest Total Premium: {latest_total:.2f}",
        showarrow=False,
        font=dict(size=16, color="white"),
        align="center",
        bgcolor="black",
        borderpad=6,
        bordercolor="gray",
        borderwidth=1
    )

    # Average Total Premium (right side of center)
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.65,
        y=1.12,
        text=f"📉 Avg Total (last {last_logs_count}): {avg_last_logs:.2f}",
        showarrow=False,
        font=dict(size=14, color="white"),
        align="center",
        bgcolor="darkred",
        borderpad=6,
        bordercolor="gray",
        borderwidth=1
    )

    # Plot Total Premium
    fig.add_trace(go.Scatter(
        x=time_data,
        y=premium_data,
        mode='lines+markers',
        name='Total Premium'
    ))

    # Plot Average Line
    fig.add_trace(go.Scatter(
        x=time_data,
        y=[avg_last_logs] * len(time_data),
        mode='lines',
        name='Average Price',
        line=dict(dash='dash', color='red')
    ))

    # Plot Alert Points (only those within the max_logs range)
    alert_times = [t for t in st.session_state.alert_points["Time"] if t in time_data]
    alert_premiums = [st.session_state.alert_points["Total Premium"][i] for i, t in enumerate(st.session_state.alert_points["Time"]) if t in time_data]
    if alert_times:
        fig.add_trace(go.Scatter(
            x=alert_times,
            y=alert_premiums,
            mode='markers',
            name='Alerts',
            marker=dict(color='green', size=10, symbol='circle')
        ))

        # Add rectangles and annotations for each alert
        for alert_time, alert_premium in zip(alert_times, alert_premiums):

            fig.add_annotation(
                x=alert_time,
                y=alert_premium,
                text=f"{alert_premium:.2f}",
                showarrow=False,
                font=dict(size=12, color="black"),
                align="center",
                bgcolor="white",
                bordercolor="green",
                borderwidth=1
            )

    fig.update_layout(
        title="NIFTY Straddle Total Premium Over Time",
        xaxis_title="Time",
        yaxis_title="Total Premium",
        showlegend=True
    )

    graph_placeholder.plotly_chart(fig, use_container_width=True)
    table_placeholder.dataframe(pd.DataFrame(st.session_state.data).tail(20), use_container_width=True)

# Function to display the alert for 5 seconds
def show_alert_for_5_seconds(message, alert_time, icon="✅"):
    status_placeholder.success(f"{message} (Alert Time: {alert_time})", icon=icon)
    threading.Timer(1, lambda: status_placeholder.empty()).start()

# --- Main Monitoring Loop ---
if st.session_state.monitoring:
    while st.session_state.monitoring:
        row = getTotalStraddlePrice(api, response)

        # Store data
        st.session_state.data.append(row)
        st.session_state.graph_data["Time"].append(row["Time"])
        st.session_state.graph_data["Total Premium"].append(row["Total Premium"])
        st.session_state.last_10_totals.append(row["Total Premium"])

        # Trim data based on Last Logs Count
        if len(st.session_state.last_10_totals) > st.session_state.last_logs_count:
            st.session_state.last_10_totals.pop(0)

        # Calculate average of the last logs
        avg = sum(st.session_state.last_10_totals) / len(st.session_state.last_10_totals)

        # Check if the current premium exceeds the threshold
        threshold = 1 + (st.session_state.percentage_increase / 100)
        if row["Total Premium"] >= avg * threshold :
            increase_percentage = ((row["Total Premium"] - avg) / avg) * 100

            # Add alert point
            st.session_state.alert_points["Time"].append(row["Time"])
            st.session_state.alert_points["Total Premium"].append(row["Total Premium"])

            # Show alert with time
            show_alert_for_5_seconds(
                f"🚀 Total premium increased by {increase_percentage:.2f}% over the last {st.session_state.last_logs_count} logs! "
                f"(Avg: {avg:.2f}, Current: {row['Total Premium']:.2f})",
                row["Time"]
            )

            # Play sound only if sound is enabled
            if st.session_state.sound_enabled and SOUND_AVAILABLE:
                winsound.Beep(1000, 1000)

            st.session_state.message_shown = True
        elif row["Total Premium"] < avg * threshold:
            st.session_state.message_shown = False

        # Update the display
        update_display()

        # Delay based on Set Time Delay (seconds)
        time.sleep(st.session_state.time_delay)