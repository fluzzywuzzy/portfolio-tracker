# Avanza Portfolio Tracker

This project is a lightweight public stock tracker for an Avanza portfolio.

The important security decision is architectural:

- `avanza-api` is only used locally in an export script.
- The public site is static and only reads `site/portfolio.json`.
- No Avanza credentials are ever needed in the browser or on the public host.
- The public output contains percentages and labels only, never monetary values.

Because Avanza credentials are inherently trading-capable, this is the safest practical way to share portfolio data publicly. A server that stores live Avanza credentials can never guarantee "no possibility" of trading if that server is compromised.

## Structure

- `scripts/export_portfolio.py`: logs in to Avanza and exports a sanitized JSON snapshot.
- `site/index.html`: static public page.
- `site/app.js`: renders the snapshot.
- `site/styles.css`: page styling.
- `site/portfolio.json`: generated data file that the page reads.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required:

- `AVANZA_USERNAME`
- `AVANZA_PASSWORD`
- `AVANZA_TOTP_SECRET`

Optional:

- `PORTFOLIO_TITLE`
- `PORTFOLIO_OWNER`
- `AVANZA_ACCOUNT_IDS`
- `PUBLIC_NOTE`

`AVANZA_ACCOUNT_IDS` should be a comma-separated list if you only want to publish specific accounts. If omitted, the exporter tries to include all accounts returned by the positions endpoint.

## Export Data

Run:

```bash
set -a
source .env
set +a
python3 scripts/export_portfolio.py
```

This updates `site/portfolio.json` with:

- portfolio allocation percentages
- holding-level percentage performance when available
- the 10 latest buy transactions for the included accounts

## Preview

```bash
python3 -m http.server 8000 --directory site
```

Then open:

`http://localhost:8000`

## Publish

Publish the contents of `site/` to any static host:

- GitHub Pages
- Netlify
- Cloudflare Pages
- Vercel static output

Only the generated JSON and static assets need to be public.

## Notes On Data

The exporter intentionally strips monetary values before writing the public JSON. It keeps:

- holding names
- tickers when available
- portfolio allocation percentage
- performance percentages when Avanza returns them
- timestamps and labels

The Avanza package used here exposes both read and write operations in its API docs:

- `get_accounts_positions` for read-only portfolio data
- `place_order` and other write methods for trading

This project only uses the read path in the local exporter and never exposes the client itself publicly.

Sources:

- Avanza package docs: https://qluxzz.github.io/avanza/avanza.html
- API method docs: https://qluxzz.github.io/avanza/avanza/avanza.html
