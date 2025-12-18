import pandas as pd
import re
from datetime import datetime, timedelta

# --- PARSEO Y CARGA ---
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
        df_t = pd.read_csv(trans_stream, sep=',', keep_default_na=False, quotechar='"')
    except Exception: return pd.DataFrame(), pd.DataFrame()
    
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
    if not all(col in df_t.columns for col in required_cols):
        return pd.DataFrame(), pd.DataFrame()

    if 'fee_eur' not in df_t.columns: df_t['fee_eur'] = 0.0
    
    df_t['qty'] = df_t['qty'].apply(clean_number)
    df_t['total_eur'] = df_t['total_eur'].apply(clean_number)
    df_t['fee_eur'] = df_t['fee_eur'].apply(clean_number)
    df_t['date_obj'] = pd.to_datetime(df_t['date'], format='%d-%m-%Y', errors='coerce')
    df_t = df_t.dropna(subset=['date_obj']).sort_values(by=['date_obj', 'time']).reset_index(drop=True)

    try:
        df_a = pd.read_csv(acc_stream, sep=',', keep_default_na=False)
    except Exception: return df_t, pd.DataFrame()

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
    else: df_a = pd.DataFrame()

    if not df_a.empty:
        col_map_a = {'Fecha': 'date', 'Producto': 'product', 'ISIN': 'isin', 'Descripción': 'desc'}
        df_a = df_a.rename(columns={k: v for k,v in col_map_a.items() if k in df_a.columns})
        df_a['date_obj'] = pd.to_datetime(df_a['date'], format='%d-%m-%Y', errors='coerce')
        df_a = df_a.dropna(subset=['date_obj'])

    return df_t, df_a

def check_anti_aplicacion(isin, row_index, all_transactions, min_batch_date=None):
    sale_row = all_transactions.loc[row_index]
    sale_date = sale_row['date_obj']
    start = sale_date - timedelta(days=62)
    end = sale_date + timedelta(days=62)
    
    # Common mask for ISIN and Time Window
    mask_window = (all_transactions['isin'] == isin) & \
                  (all_transactions['date_obj'] >= start) & \
                  (all_transactions['date_obj'] <= end)
    
    df_window = all_transactions[mask_window]
    
    # Future Purchases: Index > row_index
    purchases_future = df_window[(df_window.index > row_index) & (df_window['qty'] > 0)]['qty'].sum()
    
    if purchases_future > 0:
        return True

    # Check for "Old Shares Sold, New Shares Kept" scenario
    if min_batch_date and min_batch_date < start:
        # If we sold shares acquired BEFORE the window, any purchase INSIDE the window 
        # (before the sale) means we are holding onto those new shares while realizing a loss on old ones.
        purchases_in_window_before_sale = df_window[
            (df_window.index <= row_index) & 
            (df_window['qty'] > 0)
        ]['qty'].sum()
        
        if purchases_in_window_before_sale > 0:
            return True

    # Standard check (Net flow in window)
    # Past Purchases: Index <= row_index
    purchases_past = df_window[(df_window.index <= row_index) & (df_window['qty'] > 0)]['qty'].sum()
    
    # Past Sales: Index <= row_index (including current)
    sales_past = abs(df_window[(df_window.index <= row_index) & (df_window['qty'] < 0)]['qty'].sum())
    
    if purchases_past - sales_past > 0.001:
        return True
        
    return False

def find_opa_cash(df_acc, isin, date_ref):
    if df_acc.empty: return 0.0
    start = date_ref - timedelta(days=10)
    end = date_ref + timedelta(days=10)
    mask = (df_acc['isin'] == isin) & (df_acc['date_obj'] >= start) & \
           (df_acc['date_obj'] <= end) & (df_acc['amount_fix'] > 0)
    matches = df_acc[mask]
    return matches['amount_fix'].sum() if not matches.empty else 0.0

def calculate_fifo_cost(batches, shares_to_sell):
    cost_basis = 0.0
    warning = False
    min_date = None
    
    while shares_to_sell > 0.0001:
        if not batches:
            warning = True
            break
        
        batch = batches[0]
        if min_date is None:
            min_date = batch['date']
            
        if batch['qty'] > shares_to_sell:
            cost_basis += shares_to_sell * batch['unit_cost']
            batch['qty'] -= shares_to_sell
            shares_to_sell = 0
        else:
            cost_basis += batch['qty'] * batch['unit_cost']
            shares_to_sell -= batch['qty']
            batches.pop(0)
            
    return cost_basis, warning, min_date

# --- PROCESAMIENTO ANUAL ---
def process_year(df_trans, df_acc, target_year):
    portfolio = {} 
    sales_report = []
    purchases_report = [] # Nueva lista para compras
    fees_report = {'trading': 0.0, 'connectivity': 0.0}
    stats = {'wins': 0, 'losses': 0, 'blocked': 0}
    
    for idx, row in df_trans.iterrows():
        date = row['date_obj']
        if date.year > target_year: break
            
        isin = row['isin']
        qty = row['qty']
        total_eur = row['total_eur']
        fee_eur = row['fee_eur']
        prod = str(row['product'])
        
        if date.year == target_year:
            fees_report['trading'] += abs(fee_eur)

        if not isin or qty == 0: continue
        
        if isin not in portfolio: portfolio[isin] = {'batches': [], 'name': prod}
        else: portfolio[isin]['name'] = prod 
            
        if qty > 0: # COMPRA
            cost = abs(total_eur)
            unit_cost = cost / qty if qty > 0 else 0
            
            # Registrar batch FIFO
            portfolio[isin]['batches'].append({'qty': qty, 'unit_cost': unit_cost, 'date': date})
            
            # Registrar en reporte de Compras (Solo si es del año target)
            if date.year == target_year:
                purchases_report.append({
                    'date': row['date'],
                    'product': prod,
                    'isin': isin,
                    'qty': qty,
                    'price': unit_cost,
                    'total': cost,
                    'fee': fee_eur
                })
            
        elif qty < 0: # VENTA
            qty_sold = abs(qty)
            sale_proceeds = total_eur
            
            event_type = ""
            if "RTS" in prod.upper() or "DERECHO" in prod.upper():
                event_type = "DERECHOS"
            elif "OPA" in prod.upper() or "FUSION" in prod.upper():
                found_cash = find_opa_cash(df_acc, isin, date)
                if found_cash > 0:
                    sale_proceeds = found_cash
                event_type = "OPA/FUSIÓN"
            elif "CANJE" in prod.upper() or "SPLIT" in prod.upper():
                 event_type = "CANJE/SPLIT"
            elif abs(sale_proceeds) < 0.1: # Fallback for other nominal/zero-cash events
                 event_type = "CANJE/SPLIT"

            shares_to_sell = qty_sold
            cost_basis = 0.0
            min_batch_date = None
            warning = False
            
            if event_type == "DERECHOS":
                cost_basis = 0.0
            else:
                cost_basis, warning, min_batch_date = calculate_fifo_cost(portfolio[isin]['batches'], shares_to_sell)
            
            if date.year == target_year:
                pnl = sale_proceeds - cost_basis
                
                if event_type == "DERECHOS":
                    cost_basis = 0.0
                    pnl = sale_proceeds - cost_basis 

                is_blocked = False
                blocked_status = None
                unlock_date_str = None
                wash_sale_risk = False
                loss_consolidated = False
                repurchase_safe_date = None
                
                if pnl < 0:
                    is_blocked = check_anti_aplicacion(isin, idx, df_trans, min_batch_date)
                    if is_blocked:
                        event_type = f"⚠️ BLOQ (2 Meses) {event_type}".strip()
                        stats['blocked'] += abs(pnl)
                        
                        unlock_date = date + timedelta(days=62)
                        if datetime.now() < unlock_date:
                            blocked_status = 'active'
                        else:
                            blocked_status = 'released'
                        unlock_date_str = unlock_date.strftime('%d-%m-%Y')
                    else:
                        # Loss not blocked yet
                        safe_date = date + timedelta(days=62)
                        repurchase_safe_date = safe_date.strftime('%d-%m-%Y')
                        
                        if datetime.now() < safe_date:
                            wash_sale_risk = True
                        else:
                            loss_consolidated = True

                if pnl > 0: stats['wins'] += 1
                elif pnl < 0: stats['losses'] += 1
                
                sales_report.append({
                    'date': row['date'], 'product': prod, 'isin': isin, 'qty': qty_sold,
                    'sale_net': sale_proceeds, 'cost_basis': cost_basis,
                    'pnl': pnl, 'warning': warning, 'note': event_type, 'blocked': is_blocked,
                    'blocked_status': blocked_status, 'unlock_date': unlock_date_str,
                    'wash_sale_risk': wash_sale_risk, 'loss_consolidated': loss_consolidated,
                    'repurchase_safe_date': repurchase_safe_date
                })

    divs_report = []
    if not df_acc.empty:
        df_target = df_acc[df_acc['date_obj'].dt.year == target_year]
        for _, row in df_target.iterrows():
            desc = str(row['desc'])
            amt = row['amount_fix']
            curr = str(row['currency_fix'])
            if 'Dividendo' in desc or ('Retención' in desc and 'dividendo' in desc):
                divs_report.append({'date': row['date'], 'product': row['product'], 'isin': row['isin'], 'currency': curr, 'amount': amt, 'desc': desc})
            if 'conectividad' in desc.lower():
                fees_report['connectivity'] += abs(amt)

    final_divs = {}
    for d in divs_report:
        key = (d['date'], d['isin'], d['product'], d['currency'])
        if key not in final_divs: final_divs[key] = {'gross': 0.0, 'wht': 0.0}
        if 'Retención' in d['desc']: final_divs[key]['wht'] += abs(d['amount'])
        else: final_divs[key]['gross'] += d['amount']
    
    clean_divs = []
    for (dt, isin, prod, curr), val in final_divs.items():
        if val['gross'] > 0.01:
            clean_divs.append({'date': dt, 'product': prod, 'isin': isin, 'currency': curr, 'gross': val['gross'], 'wht': val['wht'], 'net': val['gross'] - val['wht']})

    clean_port = []
    port_val = 0
    for isin, data in portfolio.items():
        qty = sum(b['qty'] for b in data['batches'])
        if qty > 0.001:
            cost = sum(b['qty']*b['unit_cost'] for b in data['batches'])
            port_val += cost
            clean_port.append({'name': data['name'], 'isin': isin, 'qty': qty, 'avg_price': cost/qty, 'total_cost': cost})

    total_pnl = sum(s['pnl'] for s in sales_report if not s['blocked'])

    return {
        'sales': sales_report, 
        'purchases': purchases_report, # Nuevo
        'dividends': clean_divs, 
        'portfolio': clean_port,
        'portfolio_value': port_val, 
        'total_pnl': total_pnl, 
        'fees': fees_report, 
        'stats': stats
    }

# --- ANÁLISIS GLOBAL ---
def analyze_full_history(trans_stream, acc_stream):
    df_t, df_a = load_data_frames(trans_stream, acc_stream)
    if df_t.empty: return {}

    start_year = df_t['date_obj'].min().year
    max_data_year = df_t['date_obj'].max().year
    current_year = datetime.now().year
    end_year = max(max_data_year, current_year)
    
    years_data = {}
    global_stats = {
        'total_pnl': 0.0, 'total_divs_net': 0.0, 'total_fees': 0.0,
        'years_list': [], 'chart_pnl': [], 'chart_divs': [], 'chart_fees': [],
        'current_portfolio': [], 'current_portfolio_value': 0.0
    }

    processed_years = range(start_year, end_year + 1)
    
    for year in processed_years:
        data = process_year(df_t, df_a, year)
        
        # Guardamos si hay actividad o si es el último año
        has_activity = (data['sales'] or data['purchases'] or data['dividends'] or 
                        data['portfolio'] or data['fees']['connectivity'] > 0)
        
        if has_activity or year == end_year:
            years_data[year] = data
            
            divs_net = sum(d['net'] for d in data['dividends'])
            total_fees = data['fees']['trading'] + data['fees']['connectivity']
            
            global_stats['total_pnl'] += data['total_pnl']
            global_stats['total_divs_net'] += divs_net
            global_stats['total_fees'] += total_fees
            
            global_stats['years_list'].append(year)
            global_stats['chart_pnl'].append(round(data['total_pnl'], 2))
            global_stats['chart_divs'].append(round(divs_net, 2))
            global_stats['chart_fees'].append(round(total_fees, 2))

    if global_stats['years_list']:
        last_year = global_stats['years_list'][-1]
        global_stats['current_portfolio'] = years_data[last_year]['portfolio']
        global_stats['current_portfolio_value'] = years_data[last_year]['portfolio_value']

    return {'years': years_data, 'global': global_stats}