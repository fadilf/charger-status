"""Charger status dashboard for GWP 8 chargers.

Small Streamlit app that displays charger and port status by querying
the ChargeLab API. This file was cleaned up with clearer docstrings,
type hints, and compact helper comments for readability.
"""

import html
import re
import time
from datetime import datetime
from typing import Dict, Tuple, Optional

import requests
import streamlit as st

API_BASE = "https://api-v1-blue.chargelab.io/core/v1/chargers"

# Mapping of charger port status => (label, color)
STATUS_META: Dict[str, Tuple[str, str]] = {
    "SESSION": ("In use", "#e0663f"),
    "AVAILABLE": ("Available", "#4a9d6e"),
    "UNAVAILABLE": ("Unavailable", "#8a8378"),
    "FAULTED": ("Fault", "#c73e3e"),
    "OFFLINE": ("Offline", "#5a5650"),
    "PREPARING": ("Preparing", "#c99a2e"),
    "FINISHING": ("Finishing", "#c99a2e"),
}

st.set_page_config(page_title="GWP 8 Charger Status App", page_icon="🔌", layout="centered")

# ---- One-time global styling ----
st.markdown(
    """
    <style>
    /* Streamlit's built-in toolbar (hamburger menu, Deploy button) is a
       fixed strip pinned to the very top of the viewport. It sits above
       our content and will clip anything placed too close to the top —
       hiding it here and reclaiming the space keeps this app-bar-style
       title from being cut off, and reads cleaner for a mobile-app feel.
       Note: this also removes access to Streamlit's Settings/About menu. */
    /*[data-testid="stHeader"] { display: none; } */

    .block-container { padding-top: 2.5rem; max-width: 900px; }

    .cs-appbar {
        font-size: 19px; font-weight: 700; letter-spacing: -.01em;
        color: var(--text-color); padding-bottom: 14px; margin-bottom: 18px;
        border-bottom: 1px solid rgba(128,128,128,.15);
    }

    .cs-statusbar {
        display: flex; flex-wrap: wrap; align-items: center;
        gap: 10px 24px; margin-bottom: 20px;
    }
    .cs-statusbar .seg { display: flex; flex-direction: column; gap: 2px; white-space: nowrap; }
    .cs-statusbar .seg.grow { flex: 1; }
    .cs-statusbar .label {
        font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
        color: var(--text-color); opacity: .55; font-weight: 600;
    }
    .cs-statusbar .value { font-size: 15px; font-weight: 700; color: var(--text-color); white-space: nowrap; }
    .cs-statusbar .value .freshness { font-size: 13px; font-weight: 500; opacity: .6; }
    .cs-statusbar .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; }
    .cs-statusbar .divider { width: 1px; height: 30px; background: rgba(128,128,128,.3); margin: 0 20px; }

    .cs-cards-row {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 14px; align-items: start; margin-bottom: 20px;
    }

    /* Make cards stack earlier on narrower screens (phones/tablets).
       Adjust the max-width breakpoint as needed for your device. */
    @media (max-width: 520px) {
        .cs-cards-row { grid-template-columns: 1fr !important; }
        .cs-statusbar { gap: 8px 18px; }
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

    .cs-port.stale { animation: cs-pulse 1.1s ease-in-out infinite; }
    @keyframes cs-pulse {
        0%, 100% { opacity: .35; }
        50% { opacity: .7; }
    }

    /* Scoped to this button's key so it never leaks to other widgets. */
    .st-key-refresh_button button {
        background-color: #2563eb; border-color: #2563eb; color: #ffffff;
        min-height: 3.5rem;
    }
    .st-key-refresh_button button:hover {
        background-color: #1d4ed8; border-color: #1d4ed8; color: #ffffff;
    }
    .st-key-refresh_button button:active {
        background-color: #1e40af; border-color: #1e40af; color: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Sidebar: charger list + auto-refresh settings ----
st.sidebar.header("Chargers")
names_input = st.sidebar.text_input(
    "Comma separated, left to right", "BH-71, BH-72, DO-075"
)
charger_names = [n.strip() for n in names_input.split(",") if n.strip()]

st.sidebar.header("Auto-refresh")
mode = st.sidebar.radio(
    "Mode", ["On demand", "Auto"], index=0, horizontal=True,
)
interval = st.sidebar.number_input(
    "Every (seconds)", min_value=1, value=5, step=1,
    disabled=(mode == "On demand"),
)


def fetch_charger(name: str, timeout: float = 8.0) -> dict:
    """Fetch a charger entity by name from the remote API.

    Raises requests.RequestException or ValueError when the charger
    cannot be found. The caller should handle exceptions and display
    them to the user.
    """
    url = f"{API_BASE}?filter_eq[name]={name}&role=DRIVER"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    entities = data.get("entities", [])
    if not entities:
        raise ValueError("Not found")
    return entities[0]


def status_meta(status: Optional[str]) -> Tuple[str, str]:
    """Return a human label and color for a given raw status key."""
    return STATUS_META.get(status or "", (status or "Unknown", "#8a8378"))


st.markdown('<div class="cs-appbar">GWP 8 Chargers</div>', unsafe_allow_html=True)

status_placeholder = st.empty()
cards_placeholder = st.empty()
manual_refresh = st.button(
    "Refresh", help="Refresh now", use_container_width=True, type="primary", key="refresh_button", 
)


def build_status_html(chargers: Dict[str, dict], updated_at: Optional[datetime], fetching: bool) -> str:
    """Build the top status bar HTML fragment.

    Shows whether the UI is currently fetching and how many ports
    are in use vs total.
    """
    total_ports = sum(len(c.get("ports", [])) for c in chargers.values())
    available = sum(
        1
        for c in chargers.values()
        for p in c.get("ports", [])
        if p.get("status") == "AVAILABLE"
    )

    # Determine freshness color/label. When fetching, show an updating
    # indicator; otherwise show how long ago the last successful update
    # occurred, kept short so it reads naturally next to the clock time.
    if fetching:
        dot = "#c99a2e"
        freshness = "updating…"
    else:
        dot = "#4a9d6e"
        if updated_at:
            delta = datetime.now() - updated_at
            minutes = int(delta.total_seconds() // 60)
            if minutes < 1:
                freshness = "just now"
            elif minutes == 1:
                freshness = "1 min ago"
            else:
                freshness = f"{minutes} min ago"
        else:
            freshness = None

    updated_text = updated_at.strftime("%I:%M:%S %p") if updated_at else "—"
    freshness_html = f' <span class="freshness">· {freshness}</span>' if freshness else ""

    return f"""
    <div class="cs-statusbar">
        <div class="seg">
            <span class="label">Ports available</span>
            <span class="value">{available} / {total_ports}</span>
        </div>
        <div class="divider"></div>
        <div class="seg grow">
            <span class="label">Last updated</span>
            <span class="value"><span class="dot" style="background:{dot};"></span>{updated_text}{freshness_html}</span>
        </div>
    </div>
    """


def esc(value) -> str:
    """Safely escape a value for HTML output.

    None becomes an empty string; everything else is stringified
    and HTML-escaped.
    """
    return html.escape(str(value)) if value is not None else ""


def build_cards_html(chargers: Dict[str, dict], errors: Dict[str, str], fetching: bool) -> str:
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
            stale_class = " stale" if fetching else ""
            port_html.append(
                f"""
                <div class="cs-port{stale_class}" style="border:1px solid {color}55;background:{color}1a;">
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
    """Collapse multi-line HTML into a single line for Streamlit.

    Streamlit will interpret indented lines as code blocks, so we minify
    spacing between tags while preserving readability in source.
    """
    return re.sub(r">\s+<", "><", html_str.strip())


def render(chargers: dict, errors: dict, updated_at, fetching: bool):
    status_placeholder.markdown(compact(build_status_html(chargers, updated_at, fetching)), unsafe_allow_html=True)
    cards_placeholder.markdown(compact(build_cards_html(chargers, errors, fetching)), unsafe_allow_html=True)


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
        # Auto mode: sleep the user-selected interval and then refetch/re-render.
        time.sleep(interval)
        st.rerun()
    else:
        # On-demand mode: still rerun periodically (once per minute) so
        # the "minutes ago" status updates even when we are not fetching
        # fresh data. We do not re-fetch here; this is only to update UI.
        if st.session_state.updated_at:
            elapsed = (datetime.now() - st.session_state.updated_at).total_seconds()
            # Sleep until the next minute tick so the label increments near
            # a whole-minute boundary (but wait at least 1 second).
            wait = max(1, 60 - int(elapsed % 60))
            time.sleep(wait)
            st.rerun()