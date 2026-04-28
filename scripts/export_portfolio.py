from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avanza import Avanza
from avanza.constants import TransactionsDetailsType


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "site" / "portfolio.json"
ENV_PATH = ROOT / ".env"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_account_filter() -> set[str]:
    raw = os.getenv("AVANZA_ACCOUNT_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


def dig(value: Any, *path: str) -> Any:
    current = value
    for segment in path:
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(" ", "")
        cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_percent(value: Any) -> float | None:
    number = as_float(value)
    if number is None:
        return None
    if 0 < abs(number) < 1:
        return round(number * 100, 2)
    return round(number, 2)


def extract_position_value(position: dict[str, Any]) -> float:
    candidates = [
        ("value", "value"),
        ("value",),
        ("marketValue",),
        ("currentValue",),
        ("positionValue",),
        ("development", "currentValue"),
        ("instrument", "currentValue"),
    ]
    for path in candidates:
        number = as_float(dig(position, *path))
        if number is not None:
            return number
    return 0.0


def extract_position_acquired_value(position: dict[str, Any]) -> float | None:
    candidates = [
        ("acquiredValue", "value"),
        ("acquiredValue",),
    ]
    for path in candidates:
        number = as_float(dig(position, *path))
        if number is not None:
            return number
    return None


def extract_position_name(position: dict[str, Any]) -> str:
    candidates = [
        ("name",),
        ("instrument", "name"),
        ("instrument", "orderbook", "name"),
        ("orderbook", "name"),
        ("position", "name"),
        ("shortName",),
    ]
    for path in candidates:
        text = as_text(dig(position, *path))
        if text:
            return text
    return "Unknown holding"


def extract_position_ticker(position: dict[str, Any]) -> str | None:
    candidates = [
        ("tickerSymbol",),
        ("ticker",),
        ("instrument", "tickerSymbol"),
        ("instrument", "ticker"),
        ("instrument", "orderbook", "tickerSymbol"),
        ("instrument", "orderbook", "ticker"),
        ("orderbook", "tickerSymbol"),
        ("orderbook", "ticker"),
    ]
    for path in candidates:
        text = as_text(dig(position, *path))
        if text:
            return text
    return None


def extract_position_type(position: dict[str, Any]) -> str | None:
    candidates = [
        ("instrumentType",),
        ("type",),
        ("instrument", "type"),
        ("instrument", "orderbook", "type"),
        ("orderbook", "type"),
    ]
    for path in candidates:
        text = as_text(dig(position, *path))
        if text:
            return text
    return None


def extract_position_performance(position: dict[str, Any]) -> float | None:
    current_value = extract_position_value(position)
    acquired_value = extract_position_acquired_value(position)

    if acquired_value is not None and acquired_value > 0:
        return round(((current_value - acquired_value) / acquired_value) * 100, 2)

    candidates = [
        ("developmentPercent",),
        ("developmentInPercent",),
        ("changePercent",),
        ("performancePercent",),
        ("profitPercent",),
        ("yieldPercent",),
        ("development", "percent"),
        ("development", "valuePercent"),
        ("instrument", "changePercent"),
        ("instrument", "developmentPercent"),
    ]
    for path in candidates:
        percent = normalize_percent(dig(position, *path))
        if percent is not None:
            return percent
    return None


def extract_account_name(account: dict[str, Any]) -> str:
    candidates = [
        ("name",),
        ("accountName",),
        ("account", "name"),
    ]
    for path in candidates:
        text = as_text(dig(account, *path))
        if text:
            return text
    return "Unnamed account"


def extract_account_id(account: dict[str, Any]) -> str:
    candidates = [
        ("id",),
        ("accountId",),
        ("account", "id"),
    ]
    for path in candidates:
        text = as_text(dig(account, *path))
        if text:
            return text
    return "unknown-account"


def extract_account_positions(account: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        ("positions",),
        ("holdings",),
        ("instruments",),
    ]
    for path in candidates:
        value = dig(account, *path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def extract_accounts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        payload.get("accounts"),
        payload.get("accountPositions"),
    ]
    for value in candidates:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def build_accounts_from_positions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for bucket_name in ("withOrderbook", "withoutOrderbook"):
        positions = payload.get(bucket_name, [])
        if not isinstance(positions, list):
            continue

        for position in positions:
            if not isinstance(position, dict):
                continue

            account = position.get("account", {})
            if not isinstance(account, dict):
                continue

            account_id = as_text(account.get("id")) or "unknown-account"
            entry = grouped.setdefault(
                account_id,
                {
                    "id": account_id,
                    "name": as_text(account.get("name")) or "Unnamed account",
                    "positions": [],
                },
            )
            entry["positions"].append(position)

    return list(grouped.values())


def extract_transactions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    transactions = payload.get("transactions")
    if isinstance(transactions, list):
        return [item for item in transactions if isinstance(item, dict)]
    return []


def extract_transaction_account_id(transaction: dict[str, Any]) -> str | None:
    candidates = [
        ("account", "id"),
        ("accountId",),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text
    return None


def extract_transaction_name(transaction: dict[str, Any]) -> str:
    candidates = [
        ("instrumentName",),
        ("orderbook", "name"),
        ("description",),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text
    return "Unknown purchase"


def extract_transaction_date(transaction: dict[str, Any]) -> str | None:
    candidates = [
        ("tradeDate",),
        ("date",),
        ("settlementDate",),
        ("availabilityDate",),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text
    return None


def extract_transaction_amount(transaction: dict[str, Any]) -> float:
    candidates = [
        ("amount", "value"),
        ("amount",),
        ("priceInTransactionCurrency", "value"),
        ("priceInTradedCurrency", "value"),
        ("result", "value"),
    ]
    for path in candidates:
        number = as_float(dig(transaction, *path))
        if number is not None:
            return abs(number)
    return 0.0


def extract_recent_purchases(
    payload: dict[str, Any], included_account_ids: set[str], portfolio_total: float
) -> list[dict[str, Any]]:
    purchases: list[dict[str, Any]] = []

    for transaction in extract_transactions(payload):
        account_id = extract_transaction_account_id(transaction)
        if included_account_ids and account_id not in included_account_ids:
            continue

        amount = extract_transaction_amount(transaction)
        purchases.append(
            {
                "name": extract_transaction_name(transaction),
                "accountId": account_id,
                "tradeDate": extract_transaction_date(transaction),
                "portfolioImpactPercent": round(
                    (amount / portfolio_total) * 100, 2
                ) if portfolio_total > 0 else 0.0,
            }
        )

    purchases.sort(key=lambda purchase: purchase["tradeDate"] or "", reverse=True)
    return purchases[:10]


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    account_filter = parse_account_filter()
    raw_accounts = extract_accounts(payload)
    if not raw_accounts:
        raw_accounts = build_accounts_from_positions(payload)

    account_entries: list[dict[str, Any]] = []
    all_position_values: list[float] = []

    for account in raw_accounts:
        account_id = extract_account_id(account)
        if account_filter and account_id not in account_filter:
            continue

        positions = extract_account_positions(account)
        sanitized_positions: list[dict[str, Any]] = []
        account_total = 0.0

        for position in positions:
            current_value = max(extract_position_value(position), 0.0)
            account_total += current_value
            all_position_values.append(current_value)
            sanitized_positions.append(
                {
                    "name": extract_position_name(position),
                    "ticker": extract_position_ticker(position),
                    "type": extract_position_type(position),
                    "performancePercent": extract_position_performance(position),
                    "_privateValue": current_value,
                }
            )

        account_entries.append(
            {
                "accountId": account_id,
                "accountName": extract_account_name(account),
                "holdings": sanitized_positions,
                "_privateValue": account_total,
            }
        )

    portfolio_total = sum(all_position_values)
    included_account_ids = {
        account["accountId"] for account in account_entries if account.get("accountId")
    }

    for account in account_entries:
        account_value = account.pop("_privateValue", 0.0)
        account["allocationPercent"] = round(
            (account_value / portfolio_total) * 100, 2
        ) if portfolio_total > 0 else 0.0

        for holding in account["holdings"]:
            holding_value = holding.pop("_privateValue", 0.0)
            holding["allocationPercent"] = round(
                (holding_value / portfolio_total) * 100, 2
            ) if portfolio_total > 0 else 0.0

        account["holdings"].sort(
            key=lambda holding: holding["allocationPercent"], reverse=True
        )

    account_entries.sort(key=lambda account: account["allocationPercent"], reverse=True)

    holdings_count = sum(len(account["holdings"]) for account in account_entries)

    return {
        "title": os.getenv("PORTFOLIO_TITLE", "Portfolio Tracker"),
        "owner": os.getenv("PORTFOLIO_OWNER", "").strip(),
        "publicNote": os.getenv(
            "PUBLIC_NOTE", "Percentages only. No live account value is published."
        ).strip(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "accounts": len(account_entries),
            "holdings": holdings_count,
            "totalAllocationPercent": 100.0 if portfolio_total > 0 else 0.0,
        },
        "accounts": account_entries,
        "recentPurchases": [],
        "_privatePortfolioValue": portfolio_total,
    }


def main() -> None:
    load_dotenv(ENV_PATH)

    credentials = {
        "username": require_env("AVANZA_USERNAME"),
        "password": require_env("AVANZA_PASSWORD"),
        "totpSecret": require_env("AVANZA_TOTP_SECRET"),
    }

    client = Avanza(credentials)
    payload = to_dict(client.get_accounts_positions())
    sanitized = sanitize_payload(payload)
    included_account_ids = {
        account["accountId"] for account in sanitized["accounts"] if account.get("accountId")
    }
    portfolio_total = float(sanitized.pop("_privatePortfolioValue", 0.0))

    transactions_payload = to_dict(
        client.get_transactions_details(
            transaction_details_types=[TransactionsDetailsType.BUY],
            max_elements=50,
        )
    )
    sanitized["recentPurchases"] = extract_recent_purchases(
        transactions_payload,
        included_account_ids,
        portfolio_total,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(sanitized, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote sanitized portfolio snapshot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
