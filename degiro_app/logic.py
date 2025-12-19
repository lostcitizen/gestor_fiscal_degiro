import pandas as pd
import re
from datetime import datetime
from dataclasses import asdict
from .engine import PortfolioEngine

# --- PARSEO Y CARGA (Mantenemos estas utilidades aquí) ---
def clean_number(x):
    if pd.isna(x): return 0.0
    s = str(x).strip().replace('"', '')
    if not s: return 0.0
    s = re.sub(r'[^\d,\.-]', '', s)
    
    # If both separators are present, decide which is decimal
    if '.' in s and ',' in s:
        # The one that appears last is the decimal separator
        if s.rfind('.') > s.rfind(','):
            s = s.replace(',', '') # Comma is thousands separator
        else:
            s = s.replace('.', '') # Period is thousands separator
            s = s.replace(',', '.') # Comma is decimal separator
    elif ',' in s:
        # If only comma is present, assume it's the decimal separator
        s = s.replace(',', '.')
    elif '.' in s:
        parts = s.split('.')
        # If there are multiple dots, or one dot with 3 digits after it, treat as thousands separators
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
             s = s.replace('.', '')
        
    try: return float(s)
    except (ValueError, TypeError): return 0.0

def load_data_frames(trans_stream, acc_stream):
    try:
        # Auto-detect separator using python engine
        df_t = pd.read_csv(trans_stream, sep=None, engine='python', keep_default_na=False, quotechar='"')
    except Exception as e: 
        print(f"Error reading Transactions CSV: {e}")
        return pd.DataFrame(), pd.DataFrame()
    
    df_t.columns = [c.strip() for c in df_t.columns]
    col_map_t = {}
    for c in df_t.columns:
        if 'Fecha' in c: col_map_t[c] = 'date'
        elif 'Hora' in c: col_map_t[c] = 'time'
        elif 'ISIN' in c: col_map_t[c] = 'isin'
        elif 'Producto' in c: col_map_t[c] = 'product'
        elif 'Número' in c or 'Cantidad' in c: col_map_t[c] = 'qty'
        elif 'Total' in c and 'EUR' in c: col_map_t[c] = 'total_eur'
        elif 'Costes' in c or 'Comisión' in c: col_map_t[c] = 'fee_eur'

    df_t = df_t.rename(columns=col_map_t)

    required_cols = ['date', 'isin', 'product', 'qty', 'total_eur']
    missing_cols = [col for col in required_cols if col not in df_t.columns]
    if missing_cols:
        print(f"Transactions CSV missing columns: {missing_cols}. Found: {df_t.columns.tolist()}")
        return pd.DataFrame(), pd.DataFrame()

    if 'fee_eur' not in df_t.columns: df_t['fee_eur'] = 0.0
    
    df_t['qty'] = df_t['qty'].apply(clean_number)
    df_t['total_eur'] = df_t['total_eur'].apply(clean_number)
    df_t['fee_eur'] = df_t['fee_eur'].apply(clean_number)
    df_t['date_obj'] = pd.to_datetime(df_t['date'], format='%d-%m-%Y', errors='coerce')
    # Try alternate date format if all NaT
    if df_t['date_obj'].isna().all() and not df_t.empty:
         df_t['date_obj'] = pd.to_datetime(df_t['date'], format='%d/%m/%Y', errors='coerce')

    df_t = df_t.dropna(subset=['date_obj']).sort_values(by=['date_obj', 'time']).reset_index(drop=True)

    try:
        df_a = pd.read_csv(acc_stream, sep=None, engine='python', keep_default_na=False)
    except Exception as e: 
        print(f"Error reading Account CSV: {e}")
        return df_t, pd.DataFrame()

    df_a.columns = [c.strip() for c in df_a.columns]
    amt_col = 'amount_fix'
    curr_col = 'currency_fix'
    if 'Variación' in df_a.columns:
        loc_idx = df_a.columns.get_loc('Variación')
        df_a[curr_col] = df_a.iloc[:, loc_idx]
        df_a[amt_col] = df_a.iloc[:, loc_idx + 1].apply(clean_number)
    elif 'Importe' in df_a.columns:
        df_a[amt_col] = df_a['Importe'].apply(clean_number)
        df_a[curr_col] = 'EUR'
    else: 
        print(f"Account CSV missing amount columns ('Variación' or 'Importe'). Found: {df_a.columns.tolist()}")
        df_a = pd.DataFrame()

    if not df_a.empty:
        col_map_a = {'Fecha': 'date', 'Producto': 'product', 'ISIN': 'isin', 'Descripción': 'desc'}
        df_a = df_a.rename(columns={k: v for k,v in col_map_a.items() if k in df_a.columns})
        df_a['date_obj'] = pd.to_datetime(df_a['date'], format='%d-%m-%Y', errors='coerce')
        if df_a['date_obj'].isna().all() and not df_a.empty:
             df_a['date_obj'] = pd.to_datetime(df_a['date'], format='%d/%m/%Y', errors='coerce')
        df_a = df_a.dropna(subset=['date_obj'])

    return df_t, df_a

# --- WRAPPER DE COMPATIBILIDAD ---
# Mantenemos process_year expuesto por si algún test lo llama directamente, 
# pero idealmente deberíamos migrar los tests.
# Por ahora, implementamos analyze_full_history usando el nuevo motor.

def process_year(df_trans, df_acc, target_year):
    """
    Función legacy para mantener compatibilidad con tests unitarios antiguos.
    Crea un motor efímero y procesa todo hasta llegar al año target.
    """
    engine = PortfolioEngine(df_trans, df_acc)
    engine.process()
    
    if target_year in engine.years_data:
        stats = engine.years_data[target_year]
        # Convertir Dataclass a Dict para compatibilidad con tests viejos
        return {
            'sales': [asdict(s) for s in stats.sales],
            'purchases': stats.purchases,
            'dividends': [asdict(d) for d in stats.dividends],
            'portfolio': [asdict(p) for p in stats.portfolio],
            'portfolio_value': stats.portfolio_value,
            'total_pnl': stats.total_pnl_fiscal,
            'total_pnl_real': stats.total_pnl_real,
            'fees': {'trading': stats.fees_trading, 'connectivity': stats.fees_connectivity},
            'stats': {'wins': stats.stats_wins, 'losses': stats.stats_losses, 'blocked': stats.stats_blocked}
        }
    else:
        return {
            'sales': [], 'purchases': [], 'dividends': [], 'portfolio': [],
            'portfolio_value': 0, 'total_pnl': 0, 'total_pnl_real': 0,
            'fees': {'trading': 0, 'connectivity': 0}, 'stats': {'wins': 0, 'losses': 0, 'blocked': 0}
        }

def analyze_full_history(trans_stream, acc_stream):
    df_t, df_a = load_data_frames(trans_stream, acc_stream)
    if df_t.empty: return {}

    # Instanciar y ejecutar el nuevo Motor
    engine = PortfolioEngine(df_t, df_a)
    engine.process()

    start_year = df_t['date_obj'].min().year
    max_data_year = df_t['date_obj'].max().year
    current_year = datetime.now().year
    end_year = max(max_data_year, current_year)
    
    years_data = {}
    global_stats = {
        'total_pnl': 0.0, 'total_pnl_real': 0.0, 'total_divs_net': 0.0, 'total_fees': 0.0,
        'years_list': [], 'chart_pnl': [], 'chart_divs': [], 'chart_fees': [],
        'current_portfolio': [], 'current_portfolio_value': 0.0
    }

    # Recopilar resultados del motor
    # El motor ya tiene los datos agrupados por año en engine.years_data
    
    processed_years = range(start_year, end_year + 1)
    
    for year in processed_years:
        # Recuperar stats del motor o crear vacío si no hubo actividad ese año
        if year in engine.years_data:
            stats = engine.years_data[year]
            
            # Convertir a Dict para JSON
            data_dict = {
                'sales': [asdict(s) for s in stats.sales],
                'purchases': stats.purchases,
                'dividends': [asdict(d) for d in stats.dividends],
                'portfolio': [asdict(p) for p in stats.portfolio],
                'portfolio_value': stats.portfolio_value,
                'total_pnl': stats.total_pnl_fiscal,
                'total_pnl_real': stats.total_pnl_real,
                'fees': {'trading': stats.fees_trading, 'connectivity': stats.fees_connectivity},
                'stats': {'wins': stats.stats_wins, 'losses': stats.stats_losses, 'blocked': stats.stats_blocked}
            }
        else:
            # Año vacío
            data_dict = {
                'sales': [], 'purchases': [], 'dividends': [], 'portfolio': [],
                'portfolio_value': 0, 'total_pnl': 0, 'total_pnl_real': 0,
                'fees': {'trading': 0, 'connectivity': 0},
                'stats': {'wins': 0, 'losses': 0, 'blocked': 0}
            }

        # Guardar si hay actividad o es el último año
        # Check simple de actividad en el dict generado
        has_activity = (data_dict['sales'] or data_dict['purchases'] or data_dict['dividends'] or 
                        data_dict['portfolio'] or data_dict['fees']['connectivity'] > 0)
        
        if has_activity or year == end_year:
            years_data[year] = data_dict
            
            divs_net = sum(d['net'] for d in data_dict['dividends'])
            total_fees = data_dict['fees']['trading'] + data_dict['fees']['connectivity']
            
            global_stats['total_pnl'] += data_dict['total_pnl']
            global_stats['total_pnl_real'] += data_dict['total_pnl_real']
            global_stats['total_divs_net'] += divs_net
            global_stats['total_fees'] += total_fees
            
            global_stats['years_list'].append(year)
            global_stats['chart_pnl'].append(round(data_dict['total_pnl'], 2))
            global_stats['chart_divs'].append(round(divs_net, 2))
            global_stats['chart_fees'].append(round(total_fees, 2))

    if global_stats['years_list']:
        last_year = global_stats['years_list'][-1]
        # Usar el dict ya convertido
        if last_year in years_data:
            global_stats['current_portfolio'] = years_data[last_year]['portfolio']
            global_stats['current_portfolio_value'] = years_data[last_year]['portfolio_value']

    return {'years': years_data, 'global': global_stats}