"""
Portfolio service — handles portfolio CRUD, CSV import, snapshots, and metrics.
"""
import logging
import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.snapshot import PortfolioSnapshot
from app.utils.csv_parser import parse_csv_file
from app.utils.cache import CacheManager
from app.providers.yfinance_provider import get_yfinance_provider
from app.services.ticker_service import get_ticker_service

logger = logging.getLogger(__name__)


class PortfolioService:
    """Manages portfolio operations."""

    def __init__(self, db: Session):
        self.db = db
        self.cache = CacheManager(db)
        self.provider = get_yfinance_provider()
        self._ticker_service = get_ticker_service()

    def get_or_create_portfolio(self) -> Portfolio:
        """Get the default portfolio or create one."""
        portfolio = self.db.query(Portfolio).first()
        if not portfolio:
            portfolio = Portfolio(name="My Portfolio")
            self.db.add(portfolio)
            self.db.commit()
            self.db.refresh(portfolio)
        return portfolio

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary with basic metrics."""
        portfolio = self.get_or_create_portfolio()
        holdings = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        total_value = sum(h.current_value or 0 for h in holdings)
        total_cost = sum(h.cost_basis or 0 for h in holdings if h.cost_basis)
        total_gain = total_value - total_cost if total_cost > 0 else 0
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

        # Day change - sum of individual day changes
        day_change = 0
        for h in holdings:
            if h.current_price and h.quantity:
                cached = self.cache.get_cached_price(h.symbol)
                if cached and cached.get("change"):
                    day_change += cached["change"] * h.quantity

        day_change_pct = (day_change / total_value * 100) if total_value > 0 else 0

        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "total_value": round(total_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "total_gain_loss": round(total_gain, 2),
            "total_gain_loss_pct": round(total_gain_pct, 2),
            "day_change": round(day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
            "num_holdings": len(holdings),
            "last_updated": portfolio.updated_at,
        }

    def get_holdings(self, sort_by: str = "current_value", sort_order: str = "desc") -> List[Dict[str, Any]]:
        """Get all holdings with enriched data."""
        portfolio = self.get_or_create_portfolio()
        holdings = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        # Pass 1: resolve prices from cache fallback
        rows = []
        for h in holdings:
            cached_price = self.cache.get_cached_price_any_age(h.symbol)
            cached_price_val = cached_price.get("price") if cached_price else None
            current_price = h.current_price or cached_price_val
            current_value = h.current_value
            if current_value is None and current_price and h.quantity:
                current_value = current_price * h.quantity
            unrealized_gain = h.unrealized_gain
            unrealized_gain_pct = h.unrealized_gain_pct
            if unrealized_gain is None and current_price and h.avg_price:
                unrealized_gain = (current_price - h.avg_price) * h.quantity
            if unrealized_gain_pct is None and current_price and h.avg_price:
                unrealized_gain_pct = ((current_price - h.avg_price) / h.avg_price) * 100
            rows.append({
                "h": h,
                "cached_price": cached_price,
                "current_price": current_price,
                "current_value": current_value,
                "unrealized_gain": unrealized_gain,
                "unrealized_gain_pct": unrealized_gain_pct,
            })

        # Pass 2: compute allocations from resolved values
        total_value = sum(r["current_value"] or 0 for r in rows)
        result = []
        for r in rows:
            h = r["h"]
            current_value = r["current_value"]
            allocation = (current_value / total_value * 100) if total_value > 0 and current_value else 0
            cached_price = r["cached_price"]
            day_change = cached_price.get("change") if cached_price else None
            day_change_pct = cached_price.get("change_pct") if cached_price else None

            result.append({
                "id": h.id,
                "portfolio_id": h.portfolio_id,
                "symbol": h.symbol,
                "name": h.name,
                "quantity": h.quantity,
                "avg_price": h.avg_price,
                "cost_basis": h.cost_basis,
                "current_price": r["current_price"],
                "current_value": current_value,
                "unrealized_gain": r["unrealized_gain"],
                "unrealized_gain_pct": round(r["unrealized_gain_pct"], 2) if r["unrealized_gain_pct"] is not None else None,
                "allocation_pct": round(allocation, 2),
                "sector": h.sector,
                "industry": h.industry,
                "asset_type": h.asset_type,
                "day_change": day_change,
                "day_change_pct": day_change_pct,
                "created_at": h.created_at,
                "updated_at": h.updated_at,
            })

        # Sort
        if result:
            reverse = (sort_order == "desc")
            sort_key = sort_by if sort_by in result[0] else "current_value"
            try:
                result.sort(key=lambda x: x.get(sort_key) or 0, reverse=reverse)
            except Exception:
                pass

        return result

    async def import_csv(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Parse and preview a CSV file for import."""
        return parse_csv_file(file_content, filename)

    async def confirm_import(
        self,
        parsed_data: Dict[str, Any],
        snapshot_date: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Confirm CSV import: store holdings and create snapshot.
        Does NOT destroy previous portfolio history.
        """
        portfolio = self.get_or_create_portfolio()
        rows = parsed_data.get("rows", [])
        valid_rows = [r for r in rows if not r.get("errors") and r.get("symbol")]

        if not valid_rows:
            return {"success": False, "error": "No valid holdings to import."}

        # Create snapshot of current state BEFORE replacing
        current_holdings = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        if current_holdings:
            snapshot_data = [
                {
                    "symbol": h.symbol,
                    "name": h.name,
                    "quantity": h.quantity,
                    "avg_price": h.avg_price,
                    "cost_basis": h.cost_basis,
                    "current_value": h.current_value,
                    "unrealized_gain": h.unrealized_gain,
                    "unrealized_gain_pct": h.unrealized_gain_pct,
                }
                for h in current_holdings
            ]
            old_snapshot = PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=portfolio.updated_at or datetime.utcnow(),
                total_value=portfolio.total_value,
                total_cost_basis=portfolio.total_cost_basis,
                total_gain_loss=portfolio.total_gain_loss,
                total_gain_loss_pct=portfolio.total_gain_loss_pct,
                num_holdings=len(current_holdings),
                holdings_data=snapshot_data,
                notes="Auto-snapshot before new import",
            )
            self.db.add(old_snapshot)

        # Preserve sector/industry data from existing holdings before clearing
        existing_sectors = {}
        for h in current_holdings:
            if h.sector:
                existing_sectors[h.symbol] = {"sector": h.sector, "industry": h.industry, "asset_type": h.asset_type}

        # Clear existing holdings
        self.db.query(Holding).filter(Holding.portfolio_id == portfolio.id).delete()

        # Import new holdings
        imported = []
        total_value = 0
        total_cost = 0

        for row in valid_rows:
            # Normalize ticker from CSV using centralized service
            canonical = self._ticker_service.normalize(row["symbol"])
            saved = existing_sectors.get(canonical, {})
            holding = Holding(
                portfolio_id=portfolio.id,
                symbol=canonical,
                name=row.get("name"),
                quantity=row.get("quantity", 0),
                avg_price=row.get("avg_price"),
                cost_basis=row.get("cost_basis"),
                current_value=row.get("current_value"),
                unrealized_gain=row.get("unrealized_gain"),
                unrealized_gain_pct=row.get("unrealized_gain_pct"),
                sector=saved.get("sector"),
                industry=saved.get("industry"),
                asset_type=saved.get("asset_type"),
            )
            self.db.add(holding)
            imported.append(canonical)

            if row.get("current_value"):
                total_value += row["current_value"]
            if row.get("cost_basis"):
                total_cost += row["cost_basis"]

        # Update portfolio totals
        portfolio.total_value = total_value
        portfolio.total_cost_basis = total_cost
        portfolio.total_gain_loss = total_value - total_cost if total_cost > 0 else 0
        portfolio.total_gain_loss_pct = (
            (portfolio.total_gain_loss / total_cost * 100) if total_cost > 0 else 0
        )
        portfolio.updated_at = datetime.utcnow()

        # Create new snapshot
        new_snapshot = PortfolioSnapshot(
            portfolio_id=portfolio.id,
            snapshot_date=snapshot_date or datetime.utcnow(),
            source_file=parsed_data.get("filename"),
            total_value=total_value,
            total_cost_basis=total_cost,
            total_gain_loss=portfolio.total_gain_loss,
            total_gain_loss_pct=portfolio.total_gain_loss_pct,
            num_holdings=len(imported),
            holdings_data=[r for r in valid_rows],
            notes=notes,
        )
        self.db.add(new_snapshot)
        self.db.commit()

        # Auto-refresh prices and sector data after import
        try:
            await self.refresh_holdings_data()
        except Exception as e:
            logger.warning(f"Auto-refresh after import failed (holdings saved): {e}")

        return {
            "success": True,
            "imported_count": len(imported),
            "symbols": imported,
            "total_value": round(total_value, 2),
            "total_cost_basis": round(total_cost, 2),
        }

    async def refresh_holdings_data(self) -> Dict[str, Any]:
        """Refresh current prices and stock info for all holdings."""
        portfolio = self.get_or_create_portfolio()
        holdings = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        if not holdings:
            return {"updated": 0}

        # Normalize symbols before any provider call
        symbols = [self._ticker_service.normalize(h.symbol) for h in holdings]
        updated = 0

        # Batch fetch prices
        try:
            prices = await self.provider.get_batch_prices(symbols)
        except Exception as e:
            logger.error(f"Batch price fetch failed: {e}")
            prices = {}

        total_value = 0
        total_cost = 0

        for holding in holdings:
            try:
                # Use normalized symbol for all operations
                canonical = self._ticker_service.normalize(holding.symbol)
                # Update price
                price_data = prices.get(canonical, {})
                if price_data.get("price"):
                    holding.current_price = price_data["price"]
                    holding.current_value = holding.quantity * price_data["price"]

                    # Cache price data
                    self.cache.set_cached_price(canonical, price_data)

                    # Recalculate gain/loss
                    if holding.cost_basis and holding.cost_basis > 0:
                        holding.unrealized_gain = holding.current_value - holding.cost_basis
                        holding.unrealized_gain_pct = (
                            holding.unrealized_gain / holding.cost_basis * 100
                        )

                    updated += 1

                # Update stock info — always sync sector/industry from cache or fetch
                cached_info = self.cache.get_cached_stock_info(canonical)
                # Re-fetch if sector is missing even if cache is fresh,
                # because a previous failed fetch may have left sector=None
                if not cached_info or (not holding.sector and not cached_info.get("sector")):
                    try:
                        info = await self.provider.get_stock_info(canonical)
                        if info and not info.get("error"):
                            self.cache.set_cached_stock_info(canonical, info)
                            cached_info = info
                    except Exception as e:
                        logger.warning(f"Could not fetch info for {canonical}: {e}")

                # Always sync sector/industry from cached info (even if cache was warm)
                if cached_info and not cached_info.get("error"):
                    # Determine asset type first
                    quote_type = cached_info.get("asset_type", "")
                    is_etf = (quote_type == "ETF" or
                              cached_info.get("quoteType") == "ETF" or
                              cached_info.get("quoteType") == "etf" or
                              "ETF" in (cached_info.get("name") or ""))
                    if is_etf:
                        holding.asset_type = "etf"
                        if not holding.sector:
                            holding.sector = "ETF"
                    elif cached_info.get("sector") == "Real Estate" or "REIT" in (holding.name or ""):
                        holding.asset_type = "reit"
                        if not holding.sector:
                            holding.sector = cached_info.get("sector")
                    else:
                        if holding.asset_type != "etf" and holding.asset_type != "reit":
                            holding.asset_type = "stock"
                        if not holding.sector:
                            holding.sector = cached_info.get("sector")
                    if not holding.industry:
                        holding.industry = cached_info.get("industry")
                    if not holding.name and cached_info.get("name"):
                        holding.name = cached_info["name"]

                if holding.current_value:
                    total_value += holding.current_value
                if holding.cost_basis:
                    total_cost += holding.cost_basis

            except Exception as e:
                logger.warning(f"Error refreshing {holding.symbol}: {e}")

        # Update portfolio totals
        portfolio.total_value = total_value
        portfolio.total_cost_basis = total_cost
        portfolio.total_gain_loss = total_value - total_cost if total_cost > 0 else 0
        portfolio.total_gain_loss_pct = (
            (portfolio.total_gain_loss / total_cost * 100) if total_cost > 0 else 0
        )
        portfolio.updated_at = datetime.utcnow()
        self.db.commit()

        return {"updated": updated, "total": len(holdings)}

    def get_snapshots(self) -> List[Dict[str, Any]]:
        """Get all portfolio snapshots."""
        portfolio = self.get_or_create_portfolio()
        snapshots = self.db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.portfolio_id == portfolio.id
        ).order_by(PortfolioSnapshot.snapshot_date.desc()).all()

        return [
            {
                "id": s.id,
                "snapshot_date": s.snapshot_date,
                "source_file": s.source_file,
                "total_value": s.total_value,
                "total_cost_basis": s.total_cost_basis,
                "total_gain_loss": s.total_gain_loss,
                "total_gain_loss_pct": s.total_gain_loss_pct,
                "num_holdings": s.num_holdings,
                "notes": s.notes,
            }
            for s in snapshots
        ]

    def get_sector_allocation(self) -> Dict[str, float]:
        """Get sector allocation breakdown."""
        portfolio = self.get_or_create_portfolio()
        holdings = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        total_value = sum(h.current_value or 0 for h in holdings)
        if total_value == 0:
            return {}

        sectors = {}
        for h in holdings:
            sector = h.sector or "Unknown"
            value = h.current_value or 0
            sectors[sector] = sectors.get(sector, 0) + value

        return {
            sector: round(value / total_value * 100, 2)
            for sector, value in sorted(sectors.items(), key=lambda x: -x[1])
        }

    def get_performance_data(self) -> Dict[str, Any]:
        """Get portfolio performance metrics (single query, no redundant DB hits)."""
        portfolio = self.get_or_create_portfolio()
        holdings_db = self.db.query(Holding).filter(
            Holding.portfolio_id == portfolio.id
        ).all()

        # Build enriched holdings once
        total_value = sum(h.current_value or 0 for h in holdings_db)
        total_cost = sum(h.cost_basis or 0 for h in holdings_db if h.cost_basis)
        total_gain = total_value - total_cost if total_cost > 0 else 0
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

        day_change = 0
        enriched = []
        sectors: Dict[str, float] = {}
        for h in holdings_db:
            allocation = (h.current_value / total_value * 100) if total_value > 0 and h.current_value else 0

            cached_price = self.cache.get_cached_price(h.symbol)
            day_change_val = cached_price.get("change") if cached_price else None
            day_change_pct_val = cached_price.get("change_pct") if cached_price else None
            if day_change_val and h.quantity:
                day_change += day_change_val * h.quantity

            sector = h.sector or "Unknown"
            sectors[sector] = sectors.get(sector, 0) + (h.current_value or 0)

            enriched.append({
                "id": h.id,
                "portfolio_id": h.portfolio_id,
                "symbol": h.symbol,
                "name": h.name,
                "quantity": h.quantity,
                "avg_price": h.avg_price,
                "cost_basis": h.cost_basis,
                "current_price": h.current_price,
                "current_value": h.current_value,
                "unrealized_gain": h.unrealized_gain,
                "unrealized_gain_pct": h.unrealized_gain_pct,
                "allocation_pct": round(allocation, 2),
                "sector": h.sector,
                "industry": h.industry,
                "asset_type": h.asset_type,
                "day_change": day_change_val,
                "day_change_pct": day_change_pct_val,
                "created_at": h.created_at,
                "updated_at": h.updated_at,
            })

        day_change_pct = (day_change / total_value * 100) if total_value > 0 else 0

        sector_allocation = {
            sector: round(value / total_value * 100, 2)
            for sector, value in sorted(sectors.items(), key=lambda x: -x[1])
        } if total_value > 0 else {}

        performers = sorted(enriched, key=lambda x: x.get("unrealized_gain_pct") or 0, reverse=True)
        top = performers[:5] if performers else []
        worst = performers[-5:][::-1] if len(performers) > 5 else performers[::-1]

        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "total_value": round(total_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "total_gain_loss": round(total_gain, 2),
            "total_gain_loss_pct": round(total_gain_pct, 2),
            "day_change": round(day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
            "num_holdings": len(holdings_db),
            "last_updated": portfolio.updated_at,
            "sector_allocation": sector_allocation,
            "top_performers": top,
            "worst_performers": worst,
        }
