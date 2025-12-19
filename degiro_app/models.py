from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class Transaction:
    """Representa una fila cruda del CSV de transacciones."""
    date: datetime
    product: str
    isin: str
    qty: float
    total_eur: float
    fee_eur: float
    row_index: int # Para trazabilidad con el CSV original

@dataclass
class PortfolioBatch:
    """Un lote de acciones en cartera (FIFO bucket)."""
    quantity: float
    unit_cost: float
    date: datetime # Fecha de adquisición

@dataclass
class SaleResult:
    """Resultado fiscal de una venta."""
    date: datetime
    product: str
    isin: str
    qty: float
    sale_net: float
    cost_basis: float
    pnl: float
    warning: bool = False
    note: str = ""
    # Estado Fiscal
    blocked: bool = False
    blocked_status: Optional[str] = None # 'active', 'released'
    unlock_date: Optional[str] = None
    wash_sale_risk: bool = False
    repurchase_safe_date: Optional[str] = None
    loss_consolidated: bool = False

@dataclass
class DividendResult:
    """Resultado de un dividendo."""
    date: datetime
    product: str
    isin: str
    currency: str
    gross: float
    wht: float
    net: float
    desc: str

@dataclass
class PortfolioPosition:
    """Resumen de una posición abierta en cartera."""
    name: str
    isin: str
    qty: float
    avg_price: float
    total_cost: float

@dataclass
class YearStats:
    """Contenedor de todos los datos calculados para un año fiscal."""
    year: int
    sales: List[SaleResult] = field(default_factory=list)
    purchases: List[dict] = field(default_factory=list) # Mantenemos dict simple para compras reportadas
    dividends: List[DividendResult] = field(default_factory=list)
    portfolio: List[PortfolioPosition] = field(default_factory=list)
    portfolio_value: float = 0.0
    total_pnl_fiscal: float = 0.0
    total_pnl_real: float = 0.0
    fees_trading: float = 0.0
    fees_connectivity: float = 0.0
    stats_wins: int = 0
    stats_losses: int = 0
    stats_blocked: float = 0.0
