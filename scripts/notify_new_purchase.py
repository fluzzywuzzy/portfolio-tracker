from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from pywebpush import WebPushException, webpush


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
PORTFOLIO_PATH = ROOT / "site" / "portfolio.json"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_supabase_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/rest/v1"):
        normalized = normalized[: -len("/rest/v1")]
    return normalized


def supabase_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def load_portfolio() -> dict[str, Any]:
    return json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))


def latest_order_key(order: dict[str, Any]) -> str:
    return "|".join(
        [
            str(order.get("tradeDate", "")),
            str(order.get("name", "")),
            str(order.get("orderType", "")),
            str(order.get("accountId", "")),
            str(order.get("spotPrice", "")),
            str(order.get("priceCurrency", "")),
            str(order.get("volume", "")),
        ]
    )


def legacy_latest_order_key(order: dict[str, Any]) -> str:
    return "|".join(
        [
            str(order.get("tradeDate", "")),
            str(order.get("name", "")),
            str(order.get("orderType", "")),
            str(order.get("accountId", "")),
            str(order.get("portfolioImpactPercent", "")),
        ]
    )


def order_action_label(order: dict[str, Any]) -> str:
    order_type = str(order.get("orderType", "")).upper()
    if order_type == "SELL":
        return "sold"
    return "bought"


def get_state(
    supabase_url: str, service_key: str, state_table: str, state_key: str
) -> str | None:
    response = requests.get(
        f"{supabase_url}/rest/v1/{state_table}",
        headers=supabase_headers(service_key),
        params={"key": f"eq.{state_key}", "select": "value"},
        timeout=20,
    )
    response.raise_for_status()
    items = response.json()
    if not items:
        return None
    return items[0].get("value")


def set_state(
    supabase_url: str, service_key: str, state_table: str, state_key: str, value: str
) -> None:
    response = requests.post(
        f"{supabase_url}/rest/v1/{state_table}?on_conflict=key",
        headers={
            **supabase_headers(service_key),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=[{"key": state_key, "value": value}],
        timeout=20,
    )
    response.raise_for_status()


def get_subscriptions(
    supabase_url: str, service_key: str, subscriptions_table: str
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{supabase_url}/rest/v1/{subscriptions_table}",
        headers=supabase_headers(service_key),
        params={"select": "endpoint,subscription"},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    return [row for row in rows if isinstance(row.get("subscription"), dict)]


def delete_subscription(
    supabase_url: str, service_key: str, subscriptions_table: str, endpoint: str
) -> None:
    response = requests.delete(
        f"{supabase_url}/rest/v1/{subscriptions_table}",
        headers=supabase_headers(service_key),
        params={"endpoint": f"eq.{endpoint}"},
        timeout=20,
    )
    response.raise_for_status()


def build_notification_payload(
    portfolio: dict[str, Any], order: dict[str, Any]
) -> dict[str, str]:
    title = portfolio.get("title") or "Portfolio Tracker"
    public_site_url = os.getenv("PUBLIC_SITE_URL", "").strip() or "/"
    owner = portfolio.get("owner", "").strip()
    actor = owner or title
    action = order_action_label(order)

    return {
        "title": f"{title}: new order",
        "body": (
            f"{actor} {action} {order.get('name', 'a holding')} "
            f"({order.get('portfolioImpactPercent', 0)}% of portfolio)."
        ),
        "tag": "portfolio-order-alert",
        "url": public_site_url,
    }


def send_notifications(
    portfolio: dict[str, Any], order: dict[str, Any], subscriptions: list[dict[str, Any]]
) -> tuple[int, int]:
    payload = json.dumps(build_notification_payload(portfolio, order))
    vapid_private_key = require_env("WEB_PUSH_VAPID_PRIVATE_KEY")
    vapid_subject = require_env("WEB_PUSH_SUBJECT")

    sent = 0
    removed = 0

    supabase_url = require_env("SUPABASE_URL")
    service_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    subscriptions_table = os.getenv("SUPABASE_SUBSCRIPTIONS_TABLE", "push_subscriptions")

    for row in subscriptions:
        endpoint = row["endpoint"]
        subscription = row["subscription"]

        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_subject},
                ttl=60 * 60 * 6,
            )
            sent += 1
        except WebPushException as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code in {404, 410}:
                delete_subscription(supabase_url, service_key, subscriptions_table, endpoint)
                removed += 1
                continue
            raise

    return sent, removed


def main() -> None:
    load_dotenv(ENV_PATH)

    portfolio = load_portfolio()
    orders = portfolio.get("recentOrders") or portfolio.get("recentPurchases") or []
    if not orders:
        print("No orders in portfolio snapshot. Nothing to notify.")
        return

    order = orders[0]
    order_key = latest_order_key(order)
    legacy_order_key = legacy_latest_order_key(order)

    supabase_url = normalize_supabase_url(require_env("SUPABASE_URL"))
    service_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    state_table = os.getenv("SUPABASE_STATE_TABLE", "notification_state")
    subscriptions_table = os.getenv("SUPABASE_SUBSCRIPTIONS_TABLE", "push_subscriptions")
    state_key = os.getenv("NOTIFICATION_STATE_KEY", "latest_order")
    notify_on_first_run = os.getenv("NOTIFY_ON_FIRST_RUN", "").strip().lower() == "true"

    previous_key = get_state(supabase_url, service_key, state_table, state_key)
    if previous_key is None and state_key == "latest_order":
        previous_key = get_state(supabase_url, service_key, state_table, "latest_purchase")
    if previous_key == order_key:
        print("Latest order unchanged. No notifications sent.")
        return
    if previous_key == legacy_order_key:
        set_state(supabase_url, service_key, state_table, state_key, order_key)
        print("Migrated legacy notification state to stable order key. No notifications sent.")
        return

    if previous_key is None and not notify_on_first_run:
        set_state(supabase_url, service_key, state_table, state_key, order_key)
        print("Initialized notification state without sending alerts.")
        return

    subscriptions = get_subscriptions(supabase_url, service_key, subscriptions_table)
    if not subscriptions:
        set_state(supabase_url, service_key, state_table, state_key, order_key)
        print("No subscriptions found. State updated without sending alerts.")
        return

    sent, removed = send_notifications(portfolio, order, subscriptions)
    set_state(supabase_url, service_key, state_table, state_key, order_key)
    print(f"Sent {sent} notification(s); removed {removed} dead subscription(s).")


if __name__ == "__main__":
    main()
