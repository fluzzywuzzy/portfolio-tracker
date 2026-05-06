from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from avanza import Avanza
from avanza.constants import HttpMethod, Route, TransactionsDetailsType


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "site" / "portfolio.json"
ENV_PATH = ROOT / ".env"
TRANSACTION_HISTORY_START = date(2000, 1, 1)


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


def normalize_asset_alias(value: str) -> str:
    normalized = value.strip().upper()
    normalized = re.sub(r"[^A-Z0-9]+", "", normalized)
    return normalized


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


def extract_overview_accounts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = payload.get("accounts")
    if isinstance(accounts, list):
        return [item for item in accounts if isinstance(item, dict)]
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
    return "Unknown order"


def extract_transaction_type(transaction: dict[str, Any]) -> str | None:
    candidates = [
        ("type",),
        ("transactionType",),
        ("transactionTypeName",),
        ("orderType",),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text.upper()
    return None


def extract_transaction_asset_aliases(transaction: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    candidates = [
        (("orderbook", "id"), "ob"),
        (("isin",), "isin"),
        (("orderbook", "isin"), "isin"),
        (("instrumentName",), "name"),
        (("orderbook", "name"), "name"),
        (("description",), "name"),
    ]

    for path, prefix in candidates:
        text = as_text(dig(transaction, *path))
        if not text:
            continue

        normalized = normalize_asset_alias(text)
        if not normalized:
            continue

        alias = f"{prefix}:{normalized}"
        if alias in seen:
            continue

        seen.add(alias)
        aliases.append(alias)

    return aliases


def resolve_lots_for_aliases(
    alias_to_lots: dict[tuple[str | None, str], list[dict[str, float]]],
    account_id: str | None,
    aliases: list[str],
) -> list[dict[str, float]]:
    existing_ledgers: list[list[dict[str, float]]] = []

    for alias in aliases:
        existing = alias_to_lots.get((account_id, alias))
        if existing is not None and all(existing is not ledger for ledger in existing_ledgers):
            existing_ledgers.append(existing)

    if existing_ledgers:
        lots = existing_ledgers[0]
        for other in existing_ledgers[1:]:
            lots.extend(other)
            for key, value in list(alias_to_lots.items()):
                if value is other:
                    alias_to_lots[key] = lots
    else:
        lots = []

    for alias in aliases:
        alias_to_lots[(account_id, alias)] = lots
    return lots


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


def extract_transaction_timestamp(transaction: dict[str, Any]) -> str | None:
    candidates = [
        ("date",),
        ("tradeDate",),
        ("settlementDate",),
        ("availabilityDate",),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text
    return None


def parse_iso_date(value: Any) -> date | None:
    text = as_text(value)
    if not text:
        return None

    normalized = text.split("T", 1)[0]
    try:
        return date.fromisoformat(normalized)
    except ValueError:
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


def extract_transaction_volume(transaction: dict[str, Any]) -> float | None:
    candidates = [
        ("volume", "value"),
        ("volume",),
    ]
    for path in candidates:
        number = as_float(dig(transaction, *path))
        if number is not None and number != 0:
            return abs(number)
    return None


def extract_transaction_currency(transaction: dict[str, Any]) -> str | None:
    candidates = [
        ("priceInTradedCurrency", "unit"),
        ("priceInTransactionCurrency", "unit"),
        ("amount", "unit"),
        ("orderbook", "currency"),
    ]
    for path in candidates:
        text = as_text(dig(transaction, *path))
        if text:
            return text.upper()
    return None


def extract_transaction_unit_price(transaction: dict[str, Any]) -> float | None:
    candidates = [
        ("priceInTradedCurrency", "value"),
        ("priceInTransactionCurrency", "value"),
    ]
    for path in candidates:
        number = as_float(dig(transaction, *path))
        if number is not None and number > 0:
            return number

    amount = extract_transaction_amount(transaction)
    volume = extract_transaction_volume(transaction)
    if amount > 0 and volume and volume > 0:
        return amount / volume
    return None


def calculate_sell_match(
    order: dict[str, Any], lots: list[dict[str, Any]]
) -> tuple[float | None, int | None]:
    unit_price = order.get("spotPrice")
    volume = order.get("volume")
    if not isinstance(unit_price, (int, float)) or unit_price <= 0:
        return None, None
    if not isinstance(volume, (int, float)) or volume <= 0:
        return None, None

    remaining = float(volume)
    matched_volume = 0.0
    matched_cost = 0.0
    matched_dates: list[date] = []
    sell_date = parse_iso_date(order.get("tradeDate"))

    for lot in lots:
        lot_volume = lot["remainingVolume"]
        if lot_volume <= 0:
            continue

        matched = min(lot_volume, remaining)
        matched_volume += matched
        matched_cost += matched * lot["unitPrice"]
        lot_date = parse_iso_date(lot.get("tradeDate"))
        if matched > 0 and lot_date is not None:
            matched_dates.append(lot_date)
        remaining -= matched

        if remaining <= 0:
            break

    if remaining > 0 or matched_volume <= 0 or matched_cost <= 0:
        return None, None

    average_buy_price = matched_cost / matched_volume
    performance_percent = round(
        ((float(unit_price) - average_buy_price) / average_buy_price) * 100, 2
    )

    holding_period_days: int | None = None
    if matched_dates:
        first_buy_date = min(matched_dates)
        last_buy_date = max(matched_dates)

        if first_buy_date != last_buy_date:
            holding_period_days = max((last_buy_date - first_buy_date).days, 0)
        elif sell_date is not None:
            holding_period_days = max((sell_date - first_buy_date).days, 0)

    return performance_percent, holding_period_days


def consume_sell_volume(order: dict[str, Any], lots: list[dict[str, Any]]) -> None:
    volume = order.get("volume")
    if not isinstance(volume, (int, float)) or volume <= 0:
        return

    remaining = float(volume)
    updated_lots: list[dict[str, Any]] = []

    for lot in lots:
        if remaining <= 0:
            updated_lots.append(lot)
            continue

        lot_volume = lot["remainingVolume"]
        if lot_volume <= remaining:
            remaining -= lot_volume
            continue

        lot["remainingVolume"] = lot_volume - remaining
        remaining = 0.0
        updated_lots.append(lot)

    lots[:] = [lot for lot in updated_lots if lot["remainingVolume"] > 0]


def extract_recent_orders(
    payload: dict[str, Any], included_account_ids: set[str], portfolio_total: float
) -> list[dict[str, Any]]:
    chronological_orders: list[dict[str, Any]] = []

    for transaction in extract_transactions(payload):
        account_id = extract_transaction_account_id(transaction)
        if included_account_ids and account_id not in included_account_ids:
            continue

        order_type = extract_transaction_type(transaction)
        if order_type not in {"BUY", "SELL"}:
            continue

        amount = extract_transaction_amount(transaction)
        chronological_orders.append(
            {
                "id": as_text(transaction.get("id")) or "",
                "_sortTimestamp": extract_transaction_timestamp(transaction) or "",
                "_assetAliases": extract_transaction_asset_aliases(transaction),
                "name": extract_transaction_name(transaction),
                "orderType": order_type,
                "accountId": account_id,
                "tradeDate": extract_transaction_date(transaction),
                "spotPrice": extract_transaction_unit_price(transaction),
                "priceCurrency": extract_transaction_currency(transaction),
                "volume": extract_transaction_volume(transaction),
                "sellPerformancePercent": None,
                "matchedHoldingPeriodDays": None,
                "portfolioImpactPercent": round(
                    (amount / portfolio_total) * 100, 2
                ) if portfolio_total > 0 else 0.0,
            }
        )

    chronological_orders.sort(
        key=lambda order: (
            order.get("tradeDate") or "",
            order.get("_sortTimestamp") or "",
            order.get("id") or "",
        )
    )

    lots_by_asset: dict[tuple[str | None, str], list[dict[str, float]]] = {}

    for order in chronological_orders:
        asset_aliases = order.pop("_assetAliases", [])
        if not isinstance(asset_aliases, list):
            asset_aliases = []

        lots = resolve_lots_for_aliases(
            lots_by_asset,
            order.get("accountId"),
            [alias for alias in asset_aliases if isinstance(alias, str) and alias],
        )

        if order["orderType"] == "BUY":
            unit_price = order.get("spotPrice")
            volume = order.get("volume")
            if isinstance(unit_price, (int, float)) and unit_price > 0 and isinstance(volume, (int, float)) and volume > 0:
                lots.append(
                    {
                        "remainingVolume": float(volume),
                        "unitPrice": float(unit_price),
                        "tradeDate": order.get("tradeDate"),
                    }
                )
            continue

        (
            order["sellPerformancePercent"],
            order["matchedHoldingPeriodDays"],
        ) = calculate_sell_match(order, lots)
        consume_sell_volume(order, lots)

    chronological_orders.sort(
        key=lambda order: (
            order.get("tradeDate") or "",
            order.get("_sortTimestamp") or "",
            order.get("id") or "",
        ),
        reverse=True,
    )

    recent_orders = chronological_orders[:10]
    for order in recent_orders:
        order.pop("_sortTimestamp", None)
        order.pop("id", None)
        order.pop("volume", None)
    return recent_orders


def extract_balance_value(value: Any) -> float | None:
    if isinstance(value, dict):
        number = as_float(value.get("value"))
        if number is not None:
            return number
    return as_float(value)


def extract_ytd_performance_percent(
    overview_payload: dict[str, Any], included_account_ids: set[str]
) -> float | None:
    total_current_value = 0.0
    total_ytd_absolute = 0.0
    matched_accounts = 0

    for account in extract_overview_accounts(overview_payload):
        account_id = as_text(account.get("id"))
        if not account_id or (included_account_ids and account_id not in included_account_ids):
            continue

        performance = account.get("performance", {})
        if not isinstance(performance, dict):
            continue

        this_year = performance.get("THIS_YEAR")
        if not isinstance(this_year, dict):
            continue

        absolute_value = extract_balance_value(dig(this_year, "absolute"))
        current_value = extract_balance_value(account.get("totalValue"))
        if absolute_value is None or current_value is None:
            continue

        total_current_value += current_value
        total_ytd_absolute += absolute_value
        matched_accounts += 1

    if matched_accounts == 0:
        return None

    start_of_year_value = total_current_value - total_ytd_absolute
    if start_of_year_value <= 0:
        return None

    return round((total_ytd_absolute / start_of_year_value) * 100, 2)


def fetch_transactions_payload(
    client: Avanza,
    included_account_ids: set[str],
) -> dict[str, Any]:
    account_ids = sorted(account_id for account_id in included_account_ids if account_id)
    if account_ids:
        return client._Avanza__call(
            HttpMethod.GET,
            Route.TRANSACTIONS_DETAILS_PATH.value,
            {
                "maxElements": 1000,
                "transactionTypes": ",".join(
                    [TransactionsDetailsType.BUY.value, TransactionsDetailsType.SELL.value]
                ),
                "accountIds": ",".join(account_ids),
                "from": TRANSACTION_HISTORY_START.isoformat(),
            },
        )

    return to_dict(
        client.get_transactions_details(
            transaction_details_types=[
                TransactionsDetailsType.BUY,
                TransactionsDetailsType.SELL,
            ],
            transactions_from=TRANSACTION_HISTORY_START,
            max_elements=1000,
        )
    )


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
        "recentOrders": [],
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

    overview_payload = to_dict(client.get_overview())
    sanitized["summary"]["ytdPerformancePercent"] = extract_ytd_performance_percent(
        overview_payload,
        included_account_ids,
    )

    transactions_payload = fetch_transactions_payload(client, included_account_ids)
    sanitized["recentOrders"] = extract_recent_orders(
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
