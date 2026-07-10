import html
import re
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

# ---- One-time global styling ----
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 900px; }

    .cs-statusbar {
        display: flex; align-items: center; justify-content: space-between;
        padding-top: 10px; margin-top: 10px;
        border-top: 1px solid rgba(128,128,128,.25);
    }
    .cs-statusbar .seg { display: flex; flex-direction: column; gap: 2px; }
    .cs-statusbar .seg.grow { flex: 1; }
    .cs-statusbar .label {
        font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
        color: var(--text-color); opacity: .55; font-weight: 600;
    }
    .cs-statusbar .value { font-size: 15px; font-weight: 700; color: var(--text-color); }
    .cs-statusbar .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; }
    .cs-statusbar .divider { width: 1px; height: 30px; background: rgba(128,128,128,.3); margin: 0 20px; }

    .cs-cards-row {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 14px; align-items: start;
    }

    .cs-card {
        border: 1px solid rgba(128,128,128,.3); border-radius: 10px;
        padding: 16px 18px; background: var(--secondary-background-color);
    }
    .cs-card.error { border-color: #c73e3e88; background: #c73e3e14; }
    .cs-card-header {
        display: flex; flex-direction: column; gap: 2px;
        margin-bottom: 12px;
    }
    .cs-card-name { font-size: 16px; font-weight: 700; color: var(--text-color); }
    .cs-card-meta { font-size: 12px; color: var(--text-color); opacity: .6; }
    .cs-card-error-text { font-size: 13px; color: #d9605f; }
    .cs-card-empty { font-size: 13px; color: var(--text-color); opacity: .5; font-style: italic; }

    .cs-ports { display: flex; flex-direction: row; flex-wrap: wrap; gap: 8px; }
    .cs-port { flex: 1 1 100px; }
    .cs-port {
        border-radius: 6px; padding: 8px 12px;
        font-size: 12.5px; line-height: 1.5;
    }
    .cs-port .port-status { font-weight: 700; }
    .cs-port .port-sub { font-size: 11px; opacity: .75; color: var(--text-color); }
    .st-emotion-cache-4cktc5 {
        margin-bottom: 0rem !important;
    }
    .st-emotion-cache-4cktc5 p { margin: 0rem !important; }
    .st-emotion-cache-1ubki1d {align-content: center !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Sidebar: charger list only ----
st.sidebar.header("Chargers")
names_input = st.sidebar.text_input(
    "Comma separated, left to right", "BH-71, BH-72, DO-075"
)
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

control_container = st.container(border=True)
with control_container:
    c1, c2, c3, c4 = st.columns([2, 1, .75, .5],vertical_alignment="bottom")

    with c1:
        manual_refresh = st.button("Refresh", use_container_width=True)
    status_placeholder = st.empty()

    with c2:
        mode = st.radio(
            "Mode", ["On demand", "Auto"], index=0, horizontal=True,
            label_visibility="collapsed", width="content"
        )
    with c3:
        interval = st.number_input(
            "Every (s)", min_value=1, value=5, step=1,
            disabled=(mode == "On demand"), label_visibility="collapsed",
        )
    with c4:
        st.html("""
            <style>
                [data-testid="stColumn"]:nth-of-type(1) [data-testid="stVerticalBlock"] {
                    margin: 0px !important;
                }
            </style>
        """)
        st.write("seconds")


cards_placeholder = st.empty()


def build_status_html(chargers: dict, updated_at, fetching: bool) -> str:
    total_ports = sum(len(c.get("ports", [])) for c in chargers.values())
    in_use = sum(
        1
        for c in chargers.values()
        for p in c.get("ports", [])
        if p.get("status") == "SESSION"
    )

    if fetching:
        dot, text = "#c99a2e", "Updating…"
    else:
        dot, text = "#4a9d6e", "Up to date"

    updated_text = updated_at.strftime("%H:%M:%S") if updated_at else "—"

    return f"""
    <div class="cs-statusbar">
        <div class="seg grow">
            <span class="value"><span class="dot" style="background:{dot};"></span>{text}</span>
        </div>
        <div class="divider"></div>
        <div class="seg">
            <span class="label">Last updated</span>
            <span class="value">{updated_text}</span>
        </div>
        <div class="divider"></div>
        <div class="seg">
            <span class="label">Ports in use</span>
            <span class="value">{in_use} / {total_ports}</span>
        </div>
    </div>
    """


def esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def build_cards_html(chargers: dict, errors: dict) -> str:
    cards = []
    for name in charger_names:
        c = chargers.get(name)
        err = errors.get(name)
        safe_name = esc(name)

        if err:
            cards.append(
                f"""
                <div class="cs-card error">
                    <div class="cs-card-header">
                        <span class="cs-card-name">{safe_name}</span>
                    </div>
                    <div class="cs-card-error-text">Error: {esc(err)}</div>
                </div>
                """
            )
            continue

        if not c:
            cards.append(
                f"""
                <div class="cs-card">
                    <div class="cs-card-header">
                        <span class="cs-card-name">{safe_name}</span>
                    </div>
                    <div class="cs-card-empty">No data yet</div>
                </div>
                """
            )
            continue

        loc = c.get("location", {})
        meta = f"{esc(c.get('model', ''))} · {esc(loc.get('city', ''))}, {esc(loc.get('stateOrRegion', ''))}"

        port_html = []
        for p in c.get("ports", []):
            label, color = status_meta(p.get("status"))
            connector = (p.get("connectorLocations") or [None])[0] or (
                p.get("connectorTypes") or [""]
            )[0]
            port_html.append(
                f"""
                <div class="cs-port" style="border:1px solid {color}55;background:{color}1a;">
                    <div class="port-status" style="color:{color};">● {esc(label)}</div>
                    <div class="port-sub">Port {esc(p.get('portId'))} ({esc(connector)})</div>
                </div>
                """
            )

        cards.append(
            f"""
            <div class="cs-card">
                <div class="cs-card-header">
                    <span class="cs-card-name">{safe_name}</span>
                    <span class="cs-card-meta">{meta}</span>
                </div>
                <div class="cs-ports">{''.join(port_html)}</div>
            </div>
            """
        )

    return f'<div class="cs-cards-row">{"".join(cards)}</div>'


def compact(html_str: str) -> str:
    """Collapse an indented, multi-line HTML fragment into one whitespace-free
    line. Streamlit's markdown renderer treats any line indented 4+ spaces as
    a literal code block, so pretty-printed HTML must never reach it as-is."""
    return re.sub(r">\s+<", "><", html_str.strip())


def render(chargers: dict, errors: dict, updated_at, fetching: bool):
    status_placeholder.markdown(compact(build_status_html(chargers, updated_at, fetching)), unsafe_allow_html=True)
    cards_placeholder.markdown(compact(build_cards_html(chargers, errors)), unsafe_allow_html=True)


def poll():
    chargers, errors = {}, {}
    for name in charger_names:
        try:
            chargers[name] = fetch_charger(name)
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
    return chargers, errors, datetime.now()


# ---- Persisted state so the UI never has to go blank, and on-demand mode
# only ever fetches when asked (plus once on first load) ----
if "chargers" not in st.session_state:
    st.session_state.chargers = {}
    st.session_state.errors = {}
    st.session_state.updated_at = None
    st.session_state.has_fetched = False

if not charger_names:
    st.info("Add at least one charger name in the sidebar.")
else:
    should_fetch = manual_refresh or mode == "Auto" or not st.session_state.has_fetched

    # 1. Paint whatever we already know immediately — nothing ever goes blank.
    render(st.session_state.chargers, st.session_state.errors, st.session_state.updated_at, fetching=should_fetch)

    # 2. Fetch fresh data only when actually needed.
    if should_fetch:
        chargers, errors, updated_at = poll()
        st.session_state.chargers = chargers
        st.session_state.errors = errors
        st.session_state.updated_at = updated_at
        st.session_state.has_fetched = True

        # 3. Swap the same placeholders in place with the fresh data (replaces, doesn't duplicate).
        render(chargers, errors, updated_at, fetching=False)

    if mode == "Auto":
        time.sleep(interval)
        st.rerun()