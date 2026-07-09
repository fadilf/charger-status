import time
from datetime import datetime

import requests
import streamlit as st

API_BASE = "https://api-v1-blue.chargelab.io/core/v1/chargers"

STATUS_META = {
    "SESSION": ("In use", "#e0663f"),
    "AVAILABLE": ("Available", "#4a9d6e"),
    "UNAVAILABLE": ("Unavailable", "#8a8378"),
    "FAULTED": ("Fault", "#c73e3e"),
    "OFFLINE": ("Offline", "#5a5650"),
    "PREPARING": ("Preparing", "#c99a2e"),
    "FINISHING": ("Finishing", "#c99a2e"),
}

st.set_page_config(page_title="Charger Status", page_icon="🔌", layout="centered")

# ---- Sidebar settings ----
st.sidebar.header("Settings")
names_input = st.sidebar.text_input("Chargers (comma separated)", "DO-075, BH-72, BH-71")
interval = st.sidebar.number_input("Poll every (seconds)", min_value=1, value=5, step=1)
paused = st.sidebar.checkbox("Pause polling", value=False)
manual_refresh = st.sidebar.button("Refresh now")

charger_names = [n.strip() for n in names_input.split(",") if n.strip()]


def fetch_charger(name: str, timeout: float = 8.0):
    url = f"{API_BASE}?filter_eq[name]={name}&role=DRIVER"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    entities = data.get("entities", [])
    if not entities:
        raise ValueError("Not found")
    return entities[0]


def status_meta(status: str):
    return STATUS_META.get(status, (status or "Unknown", "#8a8378"))


st.title("🔌 Charger Status")
cards_placeholder = st.container()
# Refresh info lives below the cards.
footer_placeholder = st.empty()


def render(chargers: dict, errors: dict, updated_at: datetime):
    total_ports = sum(len(c.get("ports", [])) for c in chargers.values())
    in_use = sum(
        1
        for c in chargers.values()
        for p in c.get("ports", [])
        if p.get("status") == "SESSION"
    )
    refresh_line = "Polling paused" if paused else f"Auto-refreshing every {interval}s"
    footer_placeholder.caption(
        f"{refresh_line}\n\n"
        f"{in_use} / {total_ports} ports in use · updated {updated_at.strftime('%H:%M:%S')}"
    )

    with cards_placeholder:
        for name in charger_names:
            with st.container(border=True):
                c = chargers.get(name)
                err = errors.get(name)

                header_col1, header_col2 = st.columns([2, 3])
                header_col1.markdown(f"**{name}**")

                if err:
                    st.error(f"Error: {err}")
                    continue

                if not c:
                    st.caption("No data")
                    continue

                loc = c.get("location", {})
                header_col2.caption(
                    f"{c.get('model', '')} · {loc.get('city', '')}, {loc.get('stateOrRegion', '')}"
                )

                port_cols = st.columns(len(c.get("ports", [])) or 1)
                for i, p in enumerate(c.get("ports", [])):
                    label, color = status_meta(p.get("status"))
                    connector = (p.get("connectorLocations") or [None])[0] or (
                        p.get("connectorTypes") or [""]
                    )[0]
                    with port_cols[i]:
                        st.markdown(
                            f"""
                            <div style="border:1px solid {color}55;background:{color}1a;
                                        padding:8px 10px;border-radius:4px;font-size:13px;">
                                <span style="color:{color};font-weight:700;">● {label}</span><br/>
                                <span style="color:#8a8378;font-size:11px;">
                                    Port {p.get('portId')} ({connector})
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )


def poll_and_render():
    chargers, errors = {}, {}
    for name in charger_names:
        try:
            chargers[name] = fetch_charger(name)
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
    render(chargers, errors, datetime.now())


if not charger_names:
    st.info("Add at least one charger name in the sidebar.")
else:
    poll_and_render()

    if not paused:
        time.sleep(interval)
        st.rerun()
    elif manual_refresh:
        st.rerun()