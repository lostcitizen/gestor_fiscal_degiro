import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from .models import (
    Transaction, PortfolioBatch, SaleResult, DividendResult, 
    PortfolioPosition, YearStats
)

class PortfolioEngine:
    def __init__(self, df_trans: pd.DataFrame, df_acc: pd.DataFrame):
        self.df_trans = df_trans
        self.df_acc = df_acc
        
        # Estado Global
        self.portfolio: Dict[str, Dict] = {} # {isin: {'batches': [], 'name': str}}
        self.years_data: Dict[int, YearStats] = {}
        
        # Indexación para Wash Sales (optimización)
        self.trans_by_isin = self.df_trans.groupby('isin')

    def get_year_stats(self, year: int) -> YearStats:
        if year not in self.years_data:
            self.years_data[year] = YearStats(year=year)
        return self.years_data[year]

    def process(self):
        """
        Ejecuta el procesamiento cronológico de todas las transacciones (Single Pass).
        """
        # Asegurar columna time
        if 'time' not in self.df_trans.columns:
            self.df_trans['time'] = '00:00'
            
        # Asegurar orden cronológico absoluto
        self.df_trans = self.df_trans.sort_values(by=['date_obj', 'time']).reset_index(drop=True)

        current_year = None

        for idx, row in self.df_trans.iterrows():
            row_year = row['date_obj'].year
            
            # Detectar cambio de año para snapshot
            if current_year is not None and row_year > current_year:
                # Rellenar snapshots para todos los años intermedios (ej: gap 2022 -> 2024, rellenar 2022 y 2023)
                for y in range(current_year, row_year):
                    self._snapshot_portfolio(y)
            
            current_year = row_year
            self._process_row(idx, row)

        # Snapshot final para el último año (y posteriores si queremos proyectar, pero basta con el último con datos)
        if current_year is not None:
            self._snapshot_portfolio(current_year)
            
        # Procesar dividendos
        self._process_dividends()

    def _process_row(self, idx: int, row: pd.Series):
        date_obj = row['date_obj']
        year = date_obj.year
        stats = self.get_year_stats(year)
        
        isin = row['isin']
        qty = row['qty']
        total_eur = row['total_eur']
        fee_eur = row['fee_eur']
        prod_name = str(row['product'])

        if not isin or qty == 0: return

        # Inicializar cartera para este ISIN
        if isin not in self.portfolio:
            self.portfolio[isin] = {'batches': [], 'name': prod_name}
        else:
            self.portfolio[isin]['name'] = prod_name # Actualizar nombre si cambia

        if qty > 0:
            self._handle_buy(stats, isin, qty, total_eur, fee_eur, date_obj, row['date'], prod_name)
        else:
            self._handle_sell(stats, idx, isin, qty, total_eur, date_obj, row['date'], prod_name)
            
        # Acumular fees de trading
        stats.fees_trading += abs(fee_eur)

    def _handle_buy(self, stats: YearStats, isin: str, qty: float, total_eur: float, fee_eur: float, 
                   date_obj: datetime, date_str: str, prod_name: str):
        cost = abs(total_eur)
        unit_cost = cost / qty if qty > 0 else 0
        
        # FIFO Logic: Add batch
        batch = PortfolioBatch(quantity=qty, unit_cost=unit_cost, date=date_obj)
        self.portfolio[isin]['batches'].append(batch)
        
        # Report
        stats.purchases.append({
            'date': date_str,
            'product': prod_name,
            'isin': isin,
            'qty': qty,
            'price': unit_cost,
            'total': cost,
            'fee': fee_eur
        })

    def _handle_sell(self, stats: YearStats, row_idx: int, isin: str, qty: float, total_eur: float, 
                    date_obj: datetime, date_str: str, prod_name: str):
        qty_sold = abs(qty)
        sale_proceeds = total_eur
        
        # Detectar eventos especiales
        event_type, sale_proceeds = self._detect_special_event(prod_name, isin, date_obj, sale_proceeds)
        
        # Lógica FIFO
        cost_basis, warning, min_batch_date = self._consume_fifo_batches(isin, qty_sold)
        
        # Si es DERECHOS, coste es 0 (norma general simplificada)
        if event_type == "DERECHOS":
            cost_basis = 0.0
            warning = False

        pnl = sale_proceeds - cost_basis
        
        # Analizar Wash Sale (Anti-aplicación)
        is_blocked, blocked_status, unlock_date_str, wash_risk, consolidated, safe_date_str = \
            self._analyze_tax_status(isin, row_idx, pnl, date_obj, min_batch_date)

        if is_blocked:
            event_type = f"⚠️ BLOQ (2 Meses) {event_type}".strip()
            stats.stats_blocked += abs(pnl)
        
        if pnl > 0: stats.stats_wins += 1
        elif pnl < 0: stats.stats_losses += 1

        # Registrar Venta
        sale_result = SaleResult(
            date=date_obj, # Guardamos objeto datetime para ordenación posterior si hace falta
            product=prod_name,
            isin=isin,
            qty=qty_sold,
            sale_net=sale_proceeds,
            cost_basis=cost_basis,
            pnl=pnl,
            warning=warning,
            note=event_type,
            blocked=is_blocked,
            blocked_status=blocked_status,
            unlock_date=unlock_date_str,
            wash_sale_risk=wash_risk,
            loss_consolidated=consolidated,
            repurchase_safe_date=safe_date_str
        )
        stats.sales.append(sale_result)
        
        # Acumular P&L
        stats.total_pnl_real += pnl
        if not is_blocked:
            stats.total_pnl_fiscal += pnl

    def _consume_fifo_batches(self, isin: str, shares_to_sell: float) -> Tuple[float, bool, datetime]:
        cost_basis = 0.0
        warning = False
        min_date = None
        batches = self.portfolio[isin]['batches']
        
        while shares_to_sell > 0.0001:
            if not batches:
                warning = True
                break
            
            batch = batches[0]
            if min_date is None: min_date = batch.date
            
            if batch.quantity > shares_to_sell:
                cost_basis += shares_to_sell * batch.unit_cost
                batch.quantity -= shares_to_sell
                shares_to_sell = 0
            else:
                cost_basis += batch.quantity * batch.unit_cost
                shares_to_sell -= batch.quantity
                batches.pop(0)
                
        return cost_basis, warning, min_date

    def _detect_special_event(self, prod_name: str, isin: str, date_obj: datetime, original_proceeds: float):
        event_type = ""
        proceeds = original_proceeds
        
        u_prod = prod_name.upper()
        if "RTS" in u_prod or "DERECHO" in u_prod:
            event_type = "DERECHOS"
        elif "OPA" in u_prod or "FUSION" in u_prod:
            # Buscar cash OPA en Account
            found_cash = self._find_opa_cash(isin, date_obj)
            if found_cash > 0: proceeds = found_cash
            event_type = "OPA/FUSIÓN"
        elif "CANJE" in u_prod or "SPLIT" in u_prod:
            event_type = "CANJE/SPLIT"
        elif abs(proceeds) < 0.1:
             event_type = "CANJE/SPLIT"
             
        return event_type, proceeds

    def _find_opa_cash(self, isin: str, date_ref: datetime) -> float:
        if self.df_acc.empty: return 0.0
        start = date_ref - timedelta(days=10)
        end = date_ref + timedelta(days=10)
        mask = (self.df_acc['isin'] == isin) & \
               (self.df_acc['date_obj'] >= start) & \
               (self.df_acc['date_obj'] <= end) & \
               (self.df_acc['amount_fix'] > 0)
        matches = self.df_acc[mask]
        return matches['amount_fix'].sum() if not matches.empty else 0.0

    def _analyze_tax_status(self, isin: str, row_idx: int, pnl: float, date_obj: datetime, min_batch_date: datetime):
        is_blocked = False
        blocked_status = None
        unlock_date_str = None
        wash_risk = False
        consolidated = False
        safe_date_str = None
        
        if pnl >= 0:
            return False, None, None, False, False, None

        # Check Anti-Aplicación
        # Usamos self.trans_by_isin para acceso rápido vectorizado
        if isin in self.trans_by_isin.groups:
            # Obtenemos el sub-dataframe solo para este ISIN
            df_isin = self.trans_by_isin.get_group(isin)
            is_blocked = self._check_anti_aplicacion_optimized(df_isin, row_idx, date_obj, min_batch_date)
        
        safe_date = date_obj + timedelta(days=62)
        safe_date_str = safe_date.strftime('%d-%m-%Y')
        now = datetime.now()

        if is_blocked:
            unlock_date_str = safe_date_str
            blocked_status = 'active' if now < safe_date else 'released'
        else:
            if now < safe_date:
                wash_risk = True
            else:
                consolidated = True
                
        return is_blocked, blocked_status, unlock_date_str, wash_risk, consolidated, safe_date_str

    def _check_anti_aplicacion_optimized(self, df_isin: pd.DataFrame, row_idx: int, sale_date: datetime, min_batch_date: datetime):
        start = sale_date - timedelta(days=62)
        end = sale_date + timedelta(days=62)
        
        # Filtrar ventana temporal
        mask_window = (df_isin['date_obj'] >= start) & (df_isin['date_obj'] <= end)
        df_window = df_isin[mask_window]
        
        if df_window.empty: return False

        # Future Purchases: Index > row_index (en df_trans global)
        # Como df_window es un slice, usamos los índices originales
        purchases_future = df_window[(df_window.index > row_idx) & (df_window['qty'] > 0)]['qty'].sum()
        
        if purchases_future > 0: return True
        
        # Old Shares Sold scenario
        if min_batch_date and min_batch_date < start:
            purchases_in_window_before_sale = df_window[
                (df_window.index <= row_idx) & (df_window['qty'] > 0)
            ]['qty'].sum()
            if purchases_in_window_before_sale > 0: return True

        # Standard Net Flow Check
        purchases_past = df_window[(df_window.index <= row_idx) & (df_window['qty'] > 0)]['qty'].sum()
        sales_past = abs(df_window[(df_window.index <= row_idx) & (df_window['qty'] < 0)]['qty'].sum())
        
        if purchases_past - sales_past > 0.001: return True
        
        return False

    def _process_dividends(self):
        if self.df_acc.empty: return
        
        # Agrupar dividendos por (Fecha, ISIN, Producto, Divisa)
        # Para sumar 'Retención' y 'Bruto' que vienen en líneas separadas
        # Opcional: Vectorizar esto si es lento, pero suele ser rápido.
        
        raw_divs = {}
        
        for _, row in self.df_acc.iterrows():
            date_obj = row['date_obj']
            year = date_obj.year
            desc = str(row['desc'])
            amt = row['amount_fix']
            curr = str(row['currency_fix'])
            
            # Connectivity Fees logic
            if 'conectividad' in desc.lower():
                stats = self.get_year_stats(year)
                stats.fees_connectivity += abs(amt)
                continue

            # Dividend logic
            if 'Dividendo' in desc or ('Retención' in desc and 'dividendo' in desc):
                key = (year, date_obj, row['isin'], row['product'], curr)
                if key not in raw_divs:
                    raw_divs[key] = {'gross': 0.0, 'wht': 0.0}
                
                if 'Retención' in desc:
                    raw_divs[key]['wht'] += abs(amt)
                else:
                    raw_divs[key]['gross'] += amt
        
        # Distribuir resultados a los años correspondientes
        for (year, date_obj, isin, prod, curr), val in raw_divs.items():
            if val['gross'] > 0.01:
                net_val = max(0.0, val['gross'] - val['wht'])
                div_result = DividendResult(
                    date=date_obj,
                    product=prod,
                    isin=isin,
                    currency=curr,
                    gross=val['gross'],
                    wht=val['wht'],
                    net=net_val,
                    desc="Dividendo"
                )
                self.get_year_stats(year).dividends.append(div_result)

    def _snapshot_portfolio(self, year: int):
        # Crear snapshot para el año indicado (normalmente el último)
        stats = self.get_year_stats(year)
        port_val = 0.0
        
        for isin, data in self.portfolio.items():
            qty = sum(b.quantity for b in data['batches'])
            if qty > 0.001:
                cost = sum(b.quantity * b.unit_cost for b in data['batches'])
                port_val += cost
                pos = PortfolioPosition(
                    name=data['name'],
                    isin=isin,
                    qty=qty,
                    avg_price=cost/qty,
                    total_cost=cost
                )
                stats.portfolio.append(pos)
        
        stats.portfolio_value = port_val
