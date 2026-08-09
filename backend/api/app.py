from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel

from backend.database.connection import connect
from backend.database.schema import initialize_database
from backend.services.decision_journal import build_decision_journal, create_decision_update, get_decision_updates
from backend.services.financial_refresh import (
    AkshareFinancialDataProvider,
    FinancialDataError,
    FinancialDataProvider,
    refresh_stock_financials,
)
from backend.services.market_data import (
    AkshareMarketDataProvider,
    CachedMarketDataProvider,
    FallbackMarketDataProvider,
    MarketDataProvider,
    TencentMarketDataProvider,
)
from backend.services.morning_brief import (
    acknowledge_alert,
    alert_acknowledgement,
    create_follow_up_action,
    follow_up_action_trend,
    list_all_follow_up_actions,
    list_follow_up_actions,
    list_brief_snapshots,
    latest_brief_delta,
    save_brief_snapshot,
    update_brief_review_status,
    update_follow_up_action,
)
from backend.services.market_overview import build_market_overview
from backend.services.portfolio_analysis import build_portfolio_overview
from backend.services.screener import screen_stocks
from backend.services.stock_detail import build_stock_detail
from backend.services.thesis import build_thesis_overview, create_thesis_version, get_thesis_versions
from backend.services.watchlist import get_watchlist


class ThesisVersionInput(BaseModel):
    symbol: str
    thesis: str
    validation_metrics: str
    invalid_conditions: str
    review_date: str
    source_note: Optional[str] = None


class DecisionUpdateInput(BaseModel):
    event_type: str
    execution_date: Optional[str] = None
    execution_price: Optional[str] = None
    actual_result: Optional[str] = None
    review_notes: Optional[str] = None
    source_note: Optional[str] = None


class MorningBriefSnapshotInput(BaseModel):
    research_conclusion: Optional[str] = None


class MorningBriefReviewInput(BaseModel):
    reviewed: bool
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None


class MorningBriefActionInput(BaseModel):
    action_text: str
    decision_legacy_key: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "normal"


class MorningBriefActionStatusInput(BaseModel):
    completed: bool


def create_app(
    database_path: Path = Path("data/atlas.db"),
    provider: Optional[MarketDataProvider] = None,
    financial_provider: Optional[FinancialDataProvider] = None,
) -> FastAPI:
    """Create the Atlas API with a single shared market-data provider chain."""
    schema_connection = connect(database_path)
    try:
        initialize_database(schema_connection)
    finally:
        schema_connection.close()
    application = FastAPI(title="Atlas Investment Terminal API", version="2.0.0")
    market_data_provider = provider or CachedMarketDataProvider(
        FallbackMarketDataProvider(TencentMarketDataProvider(), AkshareMarketDataProvider())
    )
    financial_data_provider = financial_provider or AkshareFinancialDataProvider()

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @application.get("/api/v1/market/overview")
    def market_overview() -> dict:
        overview = build_market_overview(market_data_provider)
        overview["cache"] = market_data_provider.cache_info() if isinstance(market_data_provider, CachedMarketDataProvider) else None
        return overview

    @application.post("/api/v1/market/refresh")
    def refresh_market_overview() -> dict:
        if isinstance(market_data_provider, CachedMarketDataProvider):
            market_data_provider.clear_cache()
        overview = build_market_overview(market_data_provider)
        overview["cache"] = market_data_provider.cache_info() if isinstance(market_data_provider, CachedMarketDataProvider) else None
        return overview

    @application.get("/api/v1/morning-brief/overview")
    def morning_brief_overview() -> dict:
        connection = connect(database_path)
        try:
            market = build_market_overview(market_data_provider)
            market["cache"] = market_data_provider.cache_info() if isinstance(market_data_provider, CachedMarketDataProvider) else None
            return {
                "market": market,
                "portfolio": build_portfolio_overview(connection),
                "screener": screen_stocks(connection),
                "open_actions": list_all_follow_up_actions(connection),
                "trend_7": follow_up_action_trend(connection, 7),
                "delta": latest_brief_delta(connection),
                "history": list_brief_snapshots(connection),
                "decisions": build_decision_journal(connection),
            }
        finally:
            connection.close()

    @application.get("/api/v1/morning-brief/delta")
    def morning_brief_delta(
        current_id: Optional[int] = Query(default=None, ge=1),
        previous_id: Optional[int] = Query(default=None, ge=1),
    ) -> dict:
        connection = connect(database_path)
        try:
            return latest_brief_delta(connection, current_id, previous_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.post("/api/v1/morning-brief/snapshots", status_code=status.HTTP_201_CREATED)
    def save_morning_brief(input_data: Optional[MorningBriefSnapshotInput] = None) -> dict:
        connection = connect(database_path)
        try:
            return save_brief_snapshot(
                connection,
                build_portfolio_overview(connection),
                research_conclusion=input_data.research_conclusion if input_data else None,
            )
        finally:
            connection.close()

    @application.get("/api/v1/morning-brief/snapshots")
    def morning_brief_snapshots(limit: int = Query(default=100, ge=1, le=365)) -> dict:
        connection = connect(database_path)
        try:
            return list_brief_snapshots(connection, limit)
        finally:
            connection.close()

    @application.patch("/api/v1/morning-brief/snapshots/{snapshot_id}/review")
    def update_morning_brief_review(snapshot_id: int, input_data: MorningBriefReviewInput) -> dict:
        connection = connect(database_path)
        try:
            return update_brief_review_status(
                connection,
                snapshot_id,
                input_data.reviewed,
                input_data.reviewed_at,
                input_data.review_notes,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.post("/api/v1/morning-brief/snapshots/{snapshot_id}/actions", status_code=status.HTTP_201_CREATED)
    def create_morning_brief_action(snapshot_id: int, input_data: MorningBriefActionInput) -> dict:
        connection = connect(database_path)
        try:
            return create_follow_up_action(
                connection, snapshot_id, input_data.action_text, input_data.decision_legacy_key,
                input_data.due_date, input_data.priority,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/morning-brief/snapshots/{snapshot_id}/actions")
    def morning_brief_actions(snapshot_id: int) -> dict:
        connection = connect(database_path)
        try:
            return list_follow_up_actions(connection, snapshot_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.patch("/api/v1/morning-brief/snapshots/{snapshot_id}/actions/{action_id}")
    def update_morning_brief_action(snapshot_id: int, action_id: int, input_data: MorningBriefActionStatusInput) -> dict:
        connection = connect(database_path)
        try:
            return update_follow_up_action(connection, snapshot_id, action_id, input_data.completed)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/morning-brief/actions")
    def all_morning_brief_actions(
        status: str = Query(default="open"), due_window: str = Query(default="all")
    ) -> dict:
        connection = connect(database_path)
        try:
            return list_all_follow_up_actions(connection, status, due_window)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/morning-brief/actions/trend")
    def morning_brief_action_trend(days: int = Query(default=7, ge=1, le=30)) -> dict:
        connection = connect(database_path)
        try:
            return follow_up_action_trend(connection, days)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/alerts/{alert_key}")
    def get_alert_acknowledgement(alert_key: str) -> dict:
        connection = connect(database_path)
        try:
            return alert_acknowledgement(connection, alert_key)
        finally:
            connection.close()

    @application.post("/api/v1/alerts/{alert_key}/acknowledgements")
    def create_alert_acknowledgement(alert_key: str) -> dict:
        connection = connect(database_path)
        try:
            return acknowledge_alert(connection, alert_key)
        finally:
            connection.close()

    @application.get("/api/v1/watchlist")
    def watchlist(limit: int = Query(default=50, ge=1, le=200)) -> dict:
        connection = connect(database_path)
        try:
            return get_watchlist(connection, market_data_provider, limit)
        finally:
            connection.close()

    @application.get("/api/v1/portfolio/overview")
    def portfolio_overview() -> dict:
        connection = connect(database_path)
        try:
            return build_portfolio_overview(connection)
        finally:
            connection.close()

    @application.get("/api/v1/stocks/{symbol}")
    def stock_detail(symbol: str) -> dict:
        connection = connect(database_path)
        try:
            return build_stock_detail(connection, market_data_provider, symbol)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.post("/api/v1/stocks/{symbol}/financials/refresh")
    def refresh_stock_financial(symbol: str) -> dict:
        connection = connect(database_path)
        try:
            return refresh_stock_financials(
                connection, financial_data_provider, symbol
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except FinancialDataError as error:
            raise HTTPException(status_code=502, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/screener")
    def screener(
        max_pe_ttm: Optional[float] = Query(default=None),
        max_pb: Optional[float] = Query(default=None),
        min_profit_growth: Optional[float] = Query(default=None),
        min_gross_margin: Optional[float] = Query(default=None),
        sector: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict:
        connection = connect(database_path)
        try:
            return screen_stocks(
                connection,
                max_pe_ttm=max_pe_ttm,
                max_pb=max_pb,
                min_profit_growth=min_profit_growth,
                min_gross_margin=min_gross_margin,
                sector=sector,
                limit=limit,
            )
        finally:
            connection.close()

    @application.get("/api/v1/thesis")
    def thesis_overview() -> dict:
        connection = connect(database_path)
        try:
            return build_thesis_overview(connection)
        finally:
            connection.close()

    @application.post("/api/v1/thesis/versions", status_code=status.HTTP_201_CREATED)
    def create_thesis(input_data: ThesisVersionInput) -> dict:
        connection = connect(database_path)
        try:
            return create_thesis_version(
                connection,
                input_data.symbol,
                input_data.thesis,
                input_data.validation_metrics,
                input_data.invalid_conditions,
                input_data.review_date,
                input_data.source_note,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/thesis/{symbol}/versions")
    def thesis_versions(symbol: str) -> dict:
        connection = connect(database_path)
        try:
            return get_thesis_versions(connection, symbol)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/decisions")
    def decision_journal() -> dict:
        connection = connect(database_path)
        try:
            return build_decision_journal(connection)
        finally:
            connection.close()

    @application.post("/api/v1/decisions/{legacy_key}/updates", status_code=status.HTTP_201_CREATED)
    def create_decision_event(legacy_key: str, input_data: DecisionUpdateInput) -> dict:
        connection = connect(database_path)
        try:
            return create_decision_update(
                connection, legacy_key, input_data.event_type, input_data.execution_date,
                input_data.execution_price, input_data.actual_result, input_data.review_notes,
                input_data.source_note,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        finally:
            connection.close()

    @application.get("/api/v1/decisions/{legacy_key}/updates")
    def decision_events(legacy_key: str) -> dict:
        connection = connect(database_path)
        try:
            return get_decision_updates(connection, legacy_key)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            connection.close()

    return application


app = create_app()
