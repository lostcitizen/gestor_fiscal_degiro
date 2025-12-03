#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GESTOR FISCAL DEGIRO (FIFO + Tax Harvesting)
--------------------------------------------
Calcula P&L Realizado y Latente a partir de exportaciones CSV de Degiro.
Características:
  - Método FIFO (First-In, First-Out).
  - Coste Base incluye comisiones (Criterio Hacienda).
  - Conversión automática de divisas (USD, JPY, GBP -> EUR).
  - Detección automática de Tickers vía Yahoo Finance.
  - Soporte para múltiples archivos CSV (histórico).

Uso:
  python gestor_fiscal_degiro.py --help
"""

import pandas as pd
import glob
import os
import requests
import argparse
import sys
import yfinance as yf
from datetime import datetime

# ================= CONFIGURACIÓN ESTÁTICA =================
# Mapeo manual para ISINs que la API de Yahoo no resuelve automáticamente.
ISIN_MANUAL_MAP = {
    'US02079K3059': 'GOOGL',   # Alphabet Class A
    'US02079K1079': 'GOOG',    # Alphabet Class C
    'IE00B4L5Y983': 'SWDA.LN', # iShares Core MSCI World
    'JP3481200008': '3350.T',  # Metaplanet (Ejemplo Japón)
}

# Colores ANSI para terminal
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# ================= UTILIDADES =================

def clean_european_number(x):
    """Convierte string numérico europeo (1.234,56) a float python (1234.56)."""
    if pd.isna(x) or str(x).strip() == '': return 0.0
    x = str(x).strip().replace('.', '').replace(',', '.')
    try: return float(x)
    except ValueError: return 0.0

def get_ticker_from_isin(isin):
    """Resuelve el Ticker de Yahoo Finance a partir del ISIN."""
    if isin in ISIN_MANUAL_MAP: return ISIN_MANUAL_MAP[isin]
    
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=2)
        data = r.json()
        if 'quotes' in data and len(data['quotes']) > 0:
            return data['quotes'][0]['symbol']
    except: pass
    return None

def get_exchange_rates(currencies):
    """Descarga tipos de cambio actuales (EURxxx=X) desde Yahoo."""
    needed = [c for c in currencies if c != 'EUR']
    if not needed: return {}
    
    print(f"💱 Actualizando divisas ({', '.join(needed)})...")
    tickers = [f"EUR{c}=X" for c in needed]
    rates = {}
    try:
        # auto_adjust=False es vital para obtener precio de cierre real
        data = yf.download(tickers, period="1d", progress=False, auto_adjust=False)['Close']
        for c in needed:
            sym = f"EUR{c}=X"
            try:
                # Maneja respuesta tanto si es Series (1 activo) como DataFrame (>1 activo)
                val = data[sym].iloc[-1] if isinstance(data, pd.DataFrame) else data.iloc[-1]
                rates[c] = float(val)
            except: rates[c] = 1.0
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️ Error descargando divisas: {e}{Colors.RESET}")
    
    return rates

# ================= LÓGICA DE NEGOCIO =================

def load_data(folder_path):
    """Carga y concatena todos los CSVs encontrados en la ruta."""
    files = sorted(glob.glob(os.path.join(folder_path, "*.csv")))
    if not files:
        print(f"{Colors.RED}❌ No se encontraron archivos CSV en: {folder_path}{Colors.RESET}")
        sys.exit(1)
    
    print(f"📂 Cargando historial ({len(files)} archivos)...")
    try:
        df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    except Exception as e:
        print(f"{Colors.RED}❌ Error crítico leyendo CSVs: {e}{Colors.RESET}")
        sys.exit(1)
        
    return df

def process_fifo_accounting(df, target_year_arg=None):
    """
    Ejecuta el motor FIFO (First-In, First-Out).
    Retorna:
      - realized_pnl: DataFrame con operaciones cerradas en el año objetivo.
      - portfolio: Lista de diccionarios con la cartera viva actual.
      - fees_year: Total comisiones pagadas en el año objetivo.
      - year: El año fiscal analizado.
    """
    # 1. Normalización de columnas
    col_map = {'Fecha':'Date','Hora':'Time','ISIN':'ISIN','Producto':'Product',
               'Número':'Quantity','Total':'Total','Costes de transacción':'Fees'}
    df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
    
    # 2. Limpieza de tipos
    for c in ['Quantity','Total','Fees']: 
        df[c] = df[c].apply(clean_european_number) if c in df.columns else 0.0
        
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
    df = df.sort_values(['Date','Time'])
    
    # 3. Determinar Año Fiscal
    max_date_year = df['Date'].max().year
    target_year = int(target_year_arg) if target_year_arg else max_date_year
    print(f"🎯 Año Fiscal Objetivo: {Colors.BOLD}{target_year}{Colors.RESET}")

    # 4. Motor FIFO
    inventory = {} 
    realized_pnl = []
    fees_paid_year = 0

    for _, row in df.iterrows():
        isin = row['ISIN']
        if pd.isna(isin): continue 

        # Cash Flow de Comisiones (solo año objetivo)
        if row['Date'].year == target_year: 
            fees_paid_year += row['Fees']
            
        if isin not in inventory: 
            inventory[isin] = {'lots': [], 'name': row['Product']}

        # --- COMPRA ---
        if row['Quantity'] > 0:
            # Coste Fiscal = Valor Absoluto del Total (Precio + Comisiones)
            cost_fiscal = abs(row['Total'])
            inventory[isin]['lots'].append({
                'qty': row['Quantity'], 
                'cost_unit': cost_fiscal / row['Quantity']
            })
            inventory[isin]['name'] = row['Product']

        # --- VENTA ---
        elif row['Quantity'] < 0:
            qty_needed = abs(row['Quantity'])
            revenue_net = row['Total'] # Ingreso neto en caja
            price_unit = revenue_net / qty_needed if qty_needed > 0 else 0
            
            cost_basis = 0
            qty_sold = 0
            
            # Consumir lotes (FIFO)
            while qty_needed > 0 and inventory[isin]['lots']:
                lot = inventory[isin]['lots'][0]
                match = min(qty_needed, lot['qty'])
                lot['qty'] -= match
                qty_needed -= match
                cost_basis += match * lot['cost_unit']
                qty_sold += match
                
                # Eliminar lote agotado (con margen de error float)
                if lot['qty'] < 0.0001: inventory[isin]['lots'].pop(0)
            
            # Registrar P&L si pertenece al año objetivo
            if qty_sold > 0 and row['Date'].year == target_year:
                realized_pnl.append({
                    'Product': row['Product'], 
                    'Net_PnL': (qty_sold * price_unit) - cost_basis
                })

    # 5. Construir Cartera Viva (Holdings)
    portfolio = []
    for isin, data in inventory.items():
        qty = sum(l['qty'] for l in data['lots'])
        if qty > 0.0001:
            total_cost = sum(l['qty'] * l['cost_unit'] for l in data['lots'])
            portfolio.append({
                'ISIN': isin, 
                'Product': data['name'], 
                'Qty': qty, 
                'Total_Cost': total_cost, 
                'Avg_Cost': total_cost/qty
            })

    return pd.DataFrame(realized_pnl), pd.DataFrame(portfolio), fees_paid_year, target_year

def analyze_market_data(pf, sort_by='pnl', ascending=False):
    """
    Enriquece la cartera con datos de mercado (precios, divisas) y calcula P&L Latente.
    """
    if pf.empty: return []

    print("🌍 Conectando con mercado (Yahoo Finance)...")
    
    # 1. Obtener Tickers
    tickers_map = {}
    for isin in pf['ISIN'].unique():
        t = get_ticker_from_isin(isin)
        if t: tickers_map[isin] = t
    
    pf['Ticker'] = pf['ISIN'].map(tickers_map)
    valid = pf.dropna(subset=['Ticker']).copy()
    
    if valid.empty: 
        print(f"{Colors.YELLOW}⚠️ No se pudieron resolver Tickers para valorar la cartera.{Colors.RESET}")
        return []

    # 2. Descargar Datos
    tickers = valid['Ticker'].unique().tolist()
    prices, currs = {}, {}
    
    try:
        # Metadatos (Divisa)
        for t in tickers: 
            try: currs[t] = yf.Ticker(t).fast_info['currency']
            except: currs[t] = 'EUR'
            
        print("Precio: Buscando el último cierre válido para cada Ticker...")
        
        for t in tickers:
            try:
                # 1. Obtener el histórico de los últimos 5 días.
                data = yf.Ticker(t).history(period="5d", auto_adjust=False)
                
                # 2. Tomar el último valor de 'Close' que NO sea NaN
                #    .ffill() rellena NaNs con el último valor anterior válido.
                #    .iloc[-1] toma el último registro.
                val = data['Close'].ffill().iloc[-1]
                
                # 3. Comprobar si el valor es válido (no NaN y mayor que cero)
                if pd.isna(val) or val <= 0.0:
                    prices[t] = 0.0
                else:
                    prices[t] = float(val)
                    
            except Exception as e:
                prices[t] = 0.0
                # print(f"❌ Error al procesar el precio de {t}: {e}") # Descomentar para debug

    except Exception as e:
        print(f"{Colors.RED}Error de conexión general: {e}{Colors.RESET}")

    # 3. Tipos de Cambio
    fx = get_exchange_rates(set(currs.values()))

    # 4. Calcular Métricas
    final_rows = []
    for _, row in valid.iterrows():
        t = row['Ticker']
        qty = row['Qty']
        curr = currs.get(t, 'EUR')
        # Si el precio no pudo resolverse, prices.get(t, 0) devuelve 0, evitando NaN.
        price_loc = prices.get(t, 0)
        
        # Conversión a EUR
        rate = fx.get(curr, 1.0)
        price_eur = price_loc / rate if (curr != 'EUR' and rate > 0) else price_loc
        
        mkt_val = qty * price_eur
        cost_val = row['Total_Cost']
        pnl = mkt_val - cost_val
        pct = (pnl / cost_val * 100) if cost_val != 0 else 0.0
        
        final_rows.append({
            'Ticker': t, 
            'Product': row['Product'], 
            'Qty': qty, 
            'Price_Eur': price_eur, 
            'Avg_Cost': row['Avg_Cost'],
            'PnL': pnl, 
            'Pct': pct
        })

    # 5. Ordenación
    sort_keys = {
        'pnl': 'PnL',
        'percent': 'Pct',
        'name': 'Product',
        'qty': 'Qty'
    }
    key = sort_keys.get(sort_by, 'PnL')
    final_rows.sort(key=lambda x: x[key], reverse=not ascending)
    
    return final_rows

# ================= REPORTING =================

def print_fiscal_report(realized_df, year, fees):
    """Imprime tabla de ganancias/pérdidas realizadas."""
    if realized_df.empty:
        print(f"\nℹ️ No hay operaciones cerradas en {year}.")
    else:
        print(f"\n✅ {Colors.BOLD}RESUMEN FISCAL {year} (Operaciones Cerradas){Colors.RESET}")
        summary = realized_df.groupby('Product')['Net_PnL'].sum().sort_values()
        
        print(f"{'Producto':<40} {'Resultado Neto':>15}")
        print("-" * 57)
        for prod, val in summary.items():
            col = Colors.GREEN if val >= 0 else Colors.RED
            print(f"{col}{prod[:40]:<40} {val:>15.2f} €{Colors.RESET}")
        print("-" * 57)
        
        net_result = realized_df['Net_PnL'].sum()
        col_total = Colors.GREEN if net_result >= 0 else Colors.RED
        print(f"TOTAL REALIZADO: {col_total}{net_result:,.2f} €{Colors.RESET}")
    
    print(f"Comisiones pagadas (Cash Flow): {fees:.2f} €")

def print_portfolio_report(rows):
    """Imprime tabla de cartera viva con colores."""
    if not rows: return

    print("\n" + "="*115)
    print(f"{Colors.BOLD}📊 ESTADO DE CARTERA (LIVE){Colors.RESET}")
    print(f"{'Ticker':<9} {'Producto':<22} {'Cant.':>6} {'P.Act €':>10} {'Media €':>10} {'P&L Lat.':>12} {'% Rent.':>9}")
    print("-" * 115)
    
    total_pnl = 0
    for item in rows:
        col = Colors.GREEN if item['PnL'] >= 0 else Colors.RED
        prod = (item['Product'][:20] + '..') if len(item['Product']) > 20 else item['Product']
        
        print(f"{col}{item['Ticker']:<9} {prod:<22} {item['Qty']:>6.1f} "
              f"{item['Price_Eur']:>10.2f} {item['Avg_Cost']:>10.2f} "
              f"{item['PnL']:>12.2f} {item['Pct']:>8.2f}%{Colors.RESET}")
        
        total_pnl += item['PnL']

    print("-" * 115)
    col_tot = Colors.GREEN if total_pnl >= 0 else Colors.RED
    print(f"BALANCE LATENTE TOTAL: {col_tot}{total_pnl:,.2f} €{Colors.RESET}")

# ================= MAIN =================

def main():
    parser = argparse.ArgumentParser(description="Calculadora Fiscal Degiro (FIFO)")
    
    parser.add_argument('--dir', type=str, default='.', help='Directorio donde están los CSVs (default: actual)')
    parser.add_argument('--year', type=int, help='Año fiscal a calcular (default: último año detectado)')
    parser.add_argument('--sort', type=str, choices=['pnl', 'percent', 'name', 'qty'], default='pnl', help='Criterio de ordenación de cartera')
    parser.add_argument('--asc', action='store_true', help='Orden ascendente (por defecto es descendente/mayor a menor)')

    args = parser.parse_args()

    print(f"--- 🤖 GESTOR FISCAL DEGIRO v1.0 ---")
    
    # 1. Cargar
    df = load_data(args.dir)
    
    # 2. Procesar Fiscalidad
    realized_df, portfolio_df, fees, year = process_fifo_accounting(df, args.year)
    
    # 3. Reporte Fiscal
    print_fiscal_report(realized_df, year, fees)
    
    # 4. Análisis Mercado
    if not portfolio_df.empty:
        final_rows = analyze_market_data(portfolio_df, sort_by=args.sort, ascending=args.asc)
        print_portfolio_report(final_rows)

if __name__ == "__main__":
    main()