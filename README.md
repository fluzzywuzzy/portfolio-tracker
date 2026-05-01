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
- `scripts/notify_new_purchase.py`: sends web push notifications when the latest purchase changes.
- `scripts/generate_vapid_keys.py`: generates VAPID keys for browser push.
- `site/index.html`: static public page.
- `site/app.js`: renders the snapshot.
- `site/styles.css`: page styling.
- `site/portfolio.json`: generated data file that the page reads.
- `supabase/schema.sql`: storage schema for push subscriptions and notification state.

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

## Push Notifications

The static site can offer browser push subscriptions, but sending notifications still requires a trusted server-side secret. This repo uses:

- GitHub Pages for the public static site
- Supabase to store push subscriptions
- a GitHub Actions workflow plus `scripts/notify_new_purchase.py` to send alerts

### 1. Generate VAPID keys

Run:

```bash
python3 scripts/generate_vapid_keys.py
```

Put the generated values into `.env`:

- `WEB_PUSH_VAPID_PUBLIC_KEY`
- `WEB_PUSH_VAPID_PRIVATE_KEY`
- `WEB_PUSH_SUBJECT`

### 2. Create the Supabase tables

Create a Supabase project, then run the SQL in:

`supabase/schema.sql`

This creates:

- `push_subscriptions`
- `notification_state`

### 3. Configure the public site

Edit `site/config.js` and fill in:

- `supabaseUrl`
- `supabaseAnonKey`
- `webPushPublicKey`
- `publicSiteUrl`

These are public values and are safe to ship in the static site.

### 4. Configure local/GitHub secrets

Add these to `.env` for local testing:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `WEB_PUSH_VAPID_PRIVATE_KEY`
- `WEB_PUSH_SUBJECT`
- `PUBLIC_SITE_URL`

Add the same private values as GitHub repository secrets for the notification workflow:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `WEB_PUSH_VAPID_PRIVATE_KEY`
- `WEB_PUSH_SUBJECT`
- `PUBLIC_SITE_URL`

### 5. Test locally

After exporting the portfolio, run:

```bash
python3 scripts/notify_new_purchase.py
```

Behavior:

- first run initializes state and sends nothing
- later runs send notifications only when the top `recentPurchases[0]` entry changes
- expired subscriptions are removed automatically when the push service returns `404` or `410`

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

## GitHub Pages

This repo includes a GitHub Pages workflow at `.github/workflows/deploy-pages.yml` that publishes the `site/` directory.
It also includes `.github/workflows/notify-purchases.yml` to send push alerts when `site/portfolio.json` changes on `main`.

To enable it:

1. Push the repository to GitHub.
2. In GitHub, open `Settings` -> `Pages`.
3. Under `Build and deployment`, set `Source` to `GitHub Actions`.
4. Push to the `main` branch to deploy.

The static site includes two anti-indexing measures:

- `site/robots.txt` disallows all crawlers
- `site/index.html` includes `noindex, nofollow` meta tags

This reduces search indexing, but does not make the site private. Anyone with the URL can still access it.

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

## Raspberry Pi Automation

For a safer automated setup, keep Avanza credentials on a Raspberry Pi you control and let the Pi publish only the generated `site/portfolio.json`.

This repo includes:

- `scripts/update_and_publish.sh`: exports the snapshot, commits `site/portfolio.json` if it changed, and pushes it
- `systemd/avanza-tracker-update.service`: oneshot service for the update job
- `systemd/avanza-tracker-update.timer`: weekday schedule at 11:00, 13:00, 16:00, 19:00

### 1. Prepare the Pi

Clone the repo into your home directory so the default systemd unit paths work:

```bash
cd ~
git clone git@github.com:fluzzywuzzy/portfolio-tracker.git avanza_tracker
cd avanza_tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with your Avanza credentials and any optional settings.

The Pi also needs Git push access to the repository, typically via an SSH key that is added to GitHub.

### 2. Test the updater manually

Run:

```bash
./scripts/update_and_publish.sh
```

Behavior:

- exits safely if another run is already active
- refuses to overwrite `site/portfolio.json` if that file has local uncommitted edits
- pushes only when the generated snapshot actually changed

### 3. Install the systemd timer

Copy the units into your user systemd directory:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/avanza-tracker-update.service ~/.config/systemd/user/
cp systemd/avanza-tracker-update.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now avanza-tracker-update.timer
```

Check the schedule:

```bash
systemctl --user list-timers avanza-tracker-update.timer
```

Check logs after a run:

```bash
journalctl --user -u avanza-tracker-update.service -n 100 --no-pager
```

### 4. Keep the timer running without login

If this should keep running after reboots even when you are not logged in:

```bash
sudo loginctl enable-linger "$USER"
```

### Notes

- `systemd` uses the Pi's local timezone. Set the Pi timezone correctly to `Europe/Stockholm` if you want those wall-clock times.
- A successful push to `main` will trigger the existing GitHub Pages deployment and purchase notification workflow.
- If you later move the repo to a different path, update `WorkingDirectory` and `ExecStart` in `systemd/avanza-tracker-update.service`.

Sources:

- Avanza package docs: https://qluxzz.github.io/avanza/avanza.html
- API method docs: https://qluxzz.github.io/avanza/avanza/avanza.html
