import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

import pandas as pd


class StockMetadataError(RuntimeError):
    """Raised when the upstream provider cannot return stock metadata."""


class StockMetadataProvider:
    def get_stock_metadata(self, symbol: str) -> Dict[str, Optional[str]]:
        """Return optional name, exchange, sector and industry metadata."""


class AkshareStockMetadataProvider:
    """Enrich stock master data through AkShare when the source is reachable."""

    def __init__(
        self, fetch_info: Optional[Callable[[str], object]] = None
    ) -> None:
        self._fetch_info = fetch_info

    def get_stock_metadata(self, symbol: str) -> Dict[str, Optional[str]]:
        code = _extract_six_digit_code(symbol)
        try:
            if self._fetch_info is not None:
                frame = self._fetch_info(code)
            else:
                import akshare as ak

                frame = ak.stock_individual_info_em(symbol=code)
        except Exception as error:
            raise StockMetadataError(
                "AkShare stock metadata refresh failed: {}".format(error)
            ) from error
        return _parse_info_frame(frame, symbol)


def upsert_stock_record(
    connection: sqlite3.Connection,
    symbol: str,
    name: Optional[str] = None,
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    provider: Optional[StockMetadataProvider] = None,
) -> Dict[str, object]:
    """Create or update one stock master record with optional enrichment."""
    symbol = symbol.upper().strip()
    derived_exchange = _derive_exchange(symbol)
    requested_name = name
    metadata: Dict[str, Optional[str]] = {}
    if provider is not None:
        try:
            metadata = provider.get_stock_metadata(symbol)
        except StockMetadataError:
            metadata = {}
    name = name or metadata.get("name")
    if not name:
        raise ValueError(
            "Stock name is required when AkShare enrichment is unavailable."
        )
    exchange = exchange or metadata.get("exchange") or derived_exchange
    industry = industry or metadata.get("industry")
    sector = sector or metadata.get("sector")
    existing = connection.execute(
        "SELECT id FROM stocks WHERE symbol = ?", (symbol,)
    ).fetchone()
    if existing is not None:
        with connection:
            if requested_name is not None:
                connection.execute(
                    """
                    UPDATE stocks
                    SET name = ?,
                        exchange = COALESCE(?, exchange),
                        sector = COALESCE(?, sector),
                        industry = COALESCE(?, industry)
                    WHERE symbol = ?
                    """,
                    (requested_name, exchange, sector, industry, symbol),
                )
            else:
                connection.execute(
                    """
                    UPDATE stocks
                    SET exchange = COALESCE(?, exchange),
                        sector = COALESCE(?, sector),
                        industry = COALESCE(?, industry)
                    WHERE symbol = ?
                    """,
                    (exchange, sector, industry, symbol),
                )
    else:
        with connection:
            connection.execute(
                """
                INSERT INTO stocks (symbol, name, exchange, sector, industry)
                VALUES (?, ?, ?, ?, ?)
                """,
                (symbol, name, exchange, sector, industry),
            )
    row = connection.execute(
        """
        SELECT symbol, name, exchange, sector, industry
        FROM stocks WHERE symbol = ?
        """,
        (symbol,),
    ).fetchone()
    return {
        "status": "updated" if existing is not None else "created",
        "stock": {
            "symbol": row["symbol"],
            "name": row["name"],
            "exchange": row["exchange"],
            "sector": row["sector"],
            "industry": row["industry"],
        },
        "enriched": bool(metadata),
    }


def main(
    arguments: Optional[Sequence[str]] = None,
    provider: Optional[StockMetadataProvider] = None,
) -> int:
    parser = argparse.ArgumentParser(description="Create or update Atlas stock master records.")
    parser.add_argument("--database", type=Path, default=Path("data/atlas.db"))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--name")
    parser.add_argument("--exchange", choices=("SH", "SZ", "BJ"))
    parser.add_argument("--sector")
    parser.add_argument("--industry")
    parser.add_argument("--no-enrich", action="store_true")
    parsed = parser.parse_args(arguments)

    connection = sqlite3.connect(str(parsed.database))
    connection.row_factory = sqlite3.Row
    try:
        result = upsert_stock_record(
            connection,
            parsed.symbol,
            parsed.name,
            parsed.exchange,
            parsed.sector,
            parsed.industry,
            None if parsed.no_enrich else provider or AkshareStockMetadataProvider(),
        )
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _parse_info_frame(frame: pd.DataFrame, symbol: str) -> Dict[str, Optional[str]]:
    if frame is None or len(frame) == 0 or "item" not in frame.columns:
        raise StockMetadataError("AkShare returned no stock metadata.")
    values = {
        str(row["item"]).strip(): row["value"]
        for _, row in frame.iterrows()
    }
    name = _as_text(values.get("股票简称"))
    industry = _as_text(values.get("行业"))
    if not name:
        raise StockMetadataError("AkShare metadata did not include a stock name.")
    return {
        "name": name,
        "exchange": _derive_exchange(symbol),
        "sector": None,
        "industry": industry,
    }


def _extract_six_digit_code(symbol: str) -> str:
    match = re.search(r"\d{6}", symbol)
    if match is None:
        raise StockMetadataError("Invalid A-share symbol: " + symbol)
    return match.group(0)


def _derive_exchange(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized.endswith(".SH"):
        return "SH"
    if normalized.endswith(".SZ"):
        return "SZ"
    if normalized.endswith(".BJ"):
        return "BJ"
    code = _extract_six_digit_code(normalized)
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("0", "1", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8", "92")):
        return "BJ"
    raise ValueError("Unsupported A-share symbol: " + symbol)


def _as_text(value: object) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
