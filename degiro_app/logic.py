import pandas as pd
import re
from datetime import datetime, timedelta

# --- PARSEO Y CARGA ---
def clean_number(x):
    if pd.isna(x): return 0.0
    s = str(x).strip().replace('"', '')
    if not s: return 0.0
    s = re.sub(r'[^\d,\.-]', '', s)
    if '.' in s and ',' in s: s = s.replace('.', '').replace(',', '.')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

def load_data_frames(trans_path, acc_path):
    try:
        df_t = pd.read_csv(trans_path, sep=',', keep_default_na=False, quotechar='"')
    except: return pd.DataFrame(), pd.DataFrame()
    
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
    if 'fee_eur' not in df_t.columns: df_t['fee_eur'] = 0.0
    
    df_t['qty'] = df_t['qty'].apply(clean_number)
    df_t['total_eur'] = df_t['total_eur'].apply(clean_number)
    df_t['fee_eur'] = df_t['fee_eur'].apply(clean_number)
    df_t['date_obj'] = pd.to_datetime(df_t['date'], format='%d-%m-%Y', errors='coerce')
    df_t = df_t.dropna(subset=['date_obj']).sort_values(by=['date_obj', 'time']).reset_index(drop=True)

    try:
        df_a = pd.read_csv(acc_path, sep=',', keep_default_na=False)
    except: return df_t, pd.DataFrame()

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

def check_anti_aplicacion(isin, sale_date, all_transactions):
    start = sale_date - timedelta(days=62)
    end = sale_date + timedelta(days=62)
    mask = (all_transactions['isin'] == isin) & (all_transactions['qty'] > 0) & \
           (all_transactions['date_obj'] >= start) & (all_transactions['date_obj'] <= end)
    return not all_transactions[mask].empty

def find_opa_cash(df_acc, isin, date_ref):
    if df_acc.empty: return 0.0
    start = date_ref - timedelta(days=10)
    end = date_ref + timedelta(days=10)
    mask = (df_acc['isin'] == isin) & (df_acc['date_obj'] >= start) & \
           (df_acc['date_obj'] <= end) & (df_acc['amount_fix'] > 0)
    matches = df_acc[mask]
    return matches['amount_fix'].sum() if not matches.empty else 0.0

# --- PROCESAMIENTO ANUAL ---
def process_year(df_trans, df_acc, target_year):
    portfolio = {} 
    sales_report = []
    purchases_report = [] # Nueva lista para compras
    fees_report = {'trading': 0.0, 'connectivity': 0.0}
    stats = {'wins': 0, 'losses': 0, 'blocked': 0}
    
    for _, row in df_trans.iterrows():
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
            if "RTS" in prod.upper() or "DERECHO" in prod.upper(): event_type = "DERECHOS"
            elif abs(sale_proceeds) < 0.1:
                found_cash = find_opa_cash(df_acc, isin, date)
                if found_cash > 0:
                    sale_proceeds = found_cash
                    event_type = "OPA/FUSIÓN"
                else:
                    event_type = "CANJE/SPLIT"

            shares_to_sell = qty_sold
            cost_basis = 0.0
            warning = False
            
            while shares_to_sell > 0.0001:
                if not portfolio[isin]['batches']:
                    warning = True; break
                batch = portfolio[isin]['batches'][0]
                if batch['qty'] > shares_to_sell:
                    cost_basis += shares_to_sell * batch['unit_cost']
                    batch['qty'] -= shares_to_sell
                    shares_to_sell = 0
                else:
                    cost_basis += batch['qty'] * batch['unit_cost']
                    shares_to_sell -= batch['qty']
                    portfolio[isin]['batches'].pop(0)
            
            if date.year == target_year:
                pnl = sale_proceeds - cost_basis
                is_blocked = False
                if pnl < 0:
                    is_blocked = check_anti_aplicacion(isin, date, df_trans)
                    if is_blocked:
                        event_type = f"⚠️ BLOQ (2 Meses) {event_type}"
                        stats['blocked'] += abs(pnl)

                if pnl > 0: stats['wins'] += 1
                elif pnl < 0: stats['losses'] += 1
                
                sales_report.append({
                    'date': row['date'], 'product': prod, 'isin': isin, 'qty': qty_sold,
                    'sale_net': sale_proceeds, 'cost_basis': cost_basis,
                    'pnl': pnl, 'warning': warning, 'note': event_type, 'blocked': is_blocked
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
def analyze_full_history(trans_path, acc_path):
    df_t, df_a = load_data_frames(trans_path, acc_path)
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