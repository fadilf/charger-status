# Charger Status

A small Streamlit dashboard that polls the [ChargeLab](https://chargelab.io) API
and shows the live status of one or more EV chargers — which ports are
available, in use, offline, or faulted.

## Getting started

**Requirements:** Python 3.9+

1. Clone the repo and move into it:

   ```bash
   git clone <repo-url>
   cd charger-status
   ```

2. (Recommended) create a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the app:

   ```bash
   streamlit run charger_status.py
   ```

   Streamlit will print a local URL (usually `http://localhost:8501`) — open
   it in your browser.

## Usage

- **Chargers**: In the sidebar, enter a comma-separated list of charger names
  (e.g. `DO-075, BH-72, BH-71`). Each one is looked up via the ChargeLab API
  and rendered as a card showing its model, location, and the status of each
  port.
- **Poll every (seconds)**: How often the page auto-refreshes to pull fresh
  data.
- **Pause polling**: Stop auto-refresh; use **Refresh now** to fetch on
  demand instead.

Port statuses are color-coded:

| Status | Meaning |
| --- | --- |
| Available | Ready to use |
| In use | A charging session is active |
| Preparing / Finishing | Transitioning into or out of a session |
| Unavailable | Not currently usable |
| Offline | Not connected/reporting |
| Fault | Reporting an error |

## Notes

- Charger names must match exactly what ChargeLab reports; if a name isn't
  found, the card shows an error instead of data.
- No API key is required — the app calls ChargeLab's public read endpoint
  for driver-facing charger info.
