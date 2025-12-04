import pandas as pd
import argparse
import sys
import re
import csv
import os
import json
from datetime import datetime, timedelta

# ==========================================
# ESTILOS Y COLORES
# ==========================================
class Style:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED_TXT = '\033[91m'
    GREEN_TXT = '\033[92m'
    WHITE = '\033[97m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    
    @staticmethod
    def color_val(val):
        s = f"{val:>.2f}"
        if val > 0.001: return f"{Style.GREEN_TXT}{s}{Style.RESET}"
        if val < -0.001: return f"{Style.RED_TXT}{s}{Style.RESET}"
        return f"{Style.WHITE}{s}{Style.RESET}"

    @staticmethod
    def color_line(text, val, is_blocked=False):
        if is_blocked: return f"{Style.MAGENTA}{text}{Style.RESET}"
        if val > 0.001: return f"{Style.GREEN_TXT}{text}{Style.RESET}"
        if val < -0.001: return f"{Style.RED_TXT}{text}{Style.RESET}"
        return f"{Style.WHITE}{text}{Style.RESET}"

# ==========================================
# CONFIGURACIÓN
# ==========================================
def parse_args():
    parser = argparse.ArgumentParser(description='Gestor Fiscal DEGIRO v11 (Web App + CSV Folders)')
    parser.add_argument('--year', type=int, required=True, help='Año fiscal')
    parser.add_argument('--account', type=str, default='Account.csv', help='Ruta Account.csv')
    parser.add_argument('--transactions', type=str, default='Transactions.csv', help='Ruta Transactions.csv')
    parser.add_argument('--report', action='store_true', help='Generar CSVs y Web App')
    return parser.parse_args()

def clean_number(x):
    if pd.isna(x): return 0.0
    s = str(x).strip().replace('"', '')
    if not s: return 0.0
    s = re.sub(r'[^\d,\.-]', '', s)
    if '.' in s and ',' in s: s = s.replace('.', '').replace(',', '.')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

# ==========================================
# CARGA DE DATOS
# ==========================================
def load_data(trans_path, acc_path):
    # Transactions
    try:
        df_t = pd.read_csv(trans_path, sep=',', keep_default_na=False, quotechar='"')
    except Exception as e:
        sys.exit(f"Error cargando Transactions: {e}")
    
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

    # Account
    try:
        df_a = pd.read_csv(acc_path, sep=',', keep_default_na=False)
    except:
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
        df_a = pd.DataFrame()

    if not df_a.empty:
        col_map_a = {'Fecha': 'date', 'Producto': 'product', 'ISIN': 'isin', 'Descripción': 'desc'}
        df_a = df_a.rename(columns={k: v for k,v in col_map_a.items() if k in df_a.columns})
        df_a['date_obj'] = pd.to_datetime(df_a['date'], format='%d-%m-%Y', errors='coerce')
        df_a = df_a.dropna(subset=['date_obj'])

    return df_t, df_a

# ==========================================
# LÓGICA DE NEGOCIO
# ==========================================
def check_anti_aplicacion(isin, sale_date, all_transactions):
    start_date = sale_date - timedelta(days=62)
    end_date = sale_date + timedelta(days=62)
    mask = (
        (all_transactions['isin'] == isin) &
        (all_transactions['qty'] > 0) &
        (all_transactions['date_obj'] >= start_date) &
        (all_transactions['date_obj'] <= end_date)
    )
    return not all_transactions[mask].empty

def find_opa_cash(df_acc, isin, date_ref):
    if df_acc.empty: return 0.0
    start = date_ref - timedelta(days=10)
    end = date_ref + timedelta(days=10)
    mask = (df_acc['isin'] == isin) & (df_acc['date_obj'] >= start) & (df_acc['date_obj'] <= end) & (df_acc['amount_fix'] > 0)
    matches = df_acc[mask]
    return matches['amount_fix'].sum() if not matches.empty else 0.0

def process_portfolio(df_trans, df_acc, target_year):
    portfolio = {} 
    sales_report = []
    fees_report = {'trading': 0.0, 'connectivity': 0.0}
    stats = {'wins': 0, 'losses': 0, 'blocked': 0}
    
    print(f"⚙️  Analizando historial completo hasta 31/12/{target_year}...")
    
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
            portfolio[isin]['batches'].append({'qty': qty, 'unit_cost': unit_cost, 'date': date})
            
        elif qty < 0: # VENTA
            qty_sold = abs(qty)
            sale_proceeds = total_eur
            
            event_type = ""
            if "RTS" in prod.upper() or "DERECHO" in prod.upper() or "RIGHT" in prod.upper():
                event_type = "DERECHOS"
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

    divs_report = {}
    if not df_acc.empty:
        df_target = df_acc[df_acc['date_obj'].dt.year == target_year]
        for _, row in df_target.iterrows():
            desc = str(row['desc'])
            amt = row['amount_fix']
            curr = str(row['currency_fix'])
            
            if 'Dividendo' in desc or ('Retención' in desc and 'dividendo' in desc):
                key = (row['date'], row['isin'], row['product'], curr)
                if key not in divs_report: divs_report[key] = {'gross': 0.0, 'wht': 0.0}
                if 'Retención' in desc: divs_report[key]['wht'] += abs(amt)
                else: divs_report[key]['gross'] += amt
            
            if 'conectividad' in desc.lower():
                fees_report['connectivity'] += abs(amt)

    return sales_report, divs_report, fees_report, portfolio, stats

# ==========================================
# REPORTING (Consola)
# ==========================================
def print_report(sales, divs, fees, portfolio, stats, year):
    print("\n" + Style.BOLD + "="*115 + Style.RESET)
    print(f" 🇪🇸  {Style.BOLD}INFORME FISCAL DEGIRO {year}{Style.RESET}")
    print(Style.BOLD + "="*115 + Style.RESET)
    
    # 1. Ventas
    print(f"\n📉 {Style.BOLD}1. VENTAS Y OPAS{Style.RESET}")
    total_pnl = 0.0
    if sales:
        print(f"{'FECHA':<11} {'PRODUCTO':<28} {'P&L NETO':<10} {'NOTAS'}")
        print("-" * 115)
        for s in sales:
            note = s['note']
            if s['warning']: note = "⚠️ NO ADQ " + note
            line = f"{s['date']:<11} {str(s['product'])[:28]:<28} {s['pnl']:<10.2f} {note}"
            print(Style.color_line(line, s['pnl'], is_blocked=s['blocked']))
            if not s['blocked']: total_pnl += s['pnl']
        print("-" * 115)
        print(f"TOTAL P&L: {Style.color_line(f'{total_pnl:.2f} EUR', total_pnl)}")
    else:
        print("   (Sin movimientos)")

    # 2. Dividendos
    print(f"\n💰 {Style.BOLD}2. DIVIDENDOS{Style.RESET}")
    if divs:
        print(f"{'PRODUCTO':<30} {'NETO':<10} {'DIV'}")
        for (date, _, prod, curr), d in divs.items():
            net = d['gross'] - d['wht']
            if abs(net) > 0.01:
                print(Style.color_line(f"{str(prod)[:30]:<30} {net:<10.2f} {curr}", net))

    # 3. Cartera
    print(f"\n💼 {Style.BOLD}3. CARTERA A FIN DE AÑO ({year}){Style.RESET}")
    grand_total = 0.0
    for isin, data in portfolio.items():
        qty = sum(b['qty'] for b in data['batches'])
        if qty > 0.001:
            cost = sum(b['qty']*b['unit_cost'] for b in data['batches'])
            grand_total += cost
            print(f"{data['name'][:30]:<30} Cant: {qty:<8.2f} Inv: {cost:.2f} EUR")
    print(f"TOTAL INVERTIDO: {grand_total:.2f} EUR")

# ==========================================
# EXPORTACIÓN (CSV Folders + JSON DB + HTML)
# ==========================================
def generate_web_app(all_data):
    html_content = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestor Fiscal DEGIRO</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
        .card { background-color: #1e1e1e; border: 1px solid #333; margin-bottom: 20px; }
        .table { color: #e0e0e0; }
        .table-hover tbody tr:hover { color: #fff; background-color: #333; }
        .text-green { color: #4caf50; }
        .text-red { color: #f44336; }
        .nav-tabs .nav-link { color: #aaa; }
        .nav-tabs .nav-link.active { background-color: #1e1e1e; color: #fff; border-color: #333 #333 #1e1e1e; }
        h1, h2, h3, h4 { color: #fff; }
    </style>
</head>
<body>
<div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>📊 Informe Fiscal DEGIRO</h1>
        <select id="yearSelect" class="form-select w-auto bg-dark text-white border-secondary" onchange="renderYear()">
        </select>
    </div>

    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card p-3 text-center">
                <h5>P&L Ventas</h5>
                <h2 id="kpi-pnl">0.00 €</h2>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 text-center">
                <h5>Dividendos (Neto)</h5>
                <h2 id="kpi-divs">0.00 €</h2>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 text-center">
                <h5>Valor Cartera</h5>
                <h2 id="kpi-portfolio">0.00 €</h2>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 text-center">
                <h5>Gastos</h5>
                <h2 id="kpi-fees" class="text-warning">0.00 €</h2>
            </div>
        </div>
    </div>

    <div class="row mb-4">
        <div class="col-md-8">
            <div class="card p-3">
                <h4>Evolución P&L Acumulado</h4>
                <canvas id="pnlChart"></canvas>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card p-3">
                <h4>Distribución Cartera</h4>
                <canvas id="portfolioChart"></canvas>
            </div>
        </div>
    </div>

    <ul class="nav nav-tabs" id="myTab" role="tablist">
        <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#sales">Ventas</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#divs">Dividendos</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#portfolio">Cartera</button></li>
    </ul>
    <div class="tab-content card p-3 border-top-0">
        <div class="tab-pane fade show active" id="sales">
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead><tr><th>Fecha</th><th>Producto</th><th>Cant</th><th>V.Trans</th><th>V.Adq</th><th>P&L</th><th>Notas</th></tr></thead>
                    <tbody id="sales-body"></tbody>
                </table>
            </div>
        </div>
        <div class="tab-pane fade" id="divs">
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead><tr><th>Fecha</th><th>Producto</th><th>Divisa</th><th>Bruto</th><th>Reten</th><th>Neto</th></tr></thead>
                    <tbody id="divs-body"></tbody>
                </table>
            </div>
        </div>
        <div class="tab-pane fade" id="portfolio">
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead><tr><th>Producto</th><th>ISIN</th><th>Cant</th><th>Pr.Medio</th><th>Total Inv.</th></tr></thead>
                    <tbody id="portfolio-body"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    const db = """ + json.dumps(all_data) + """;
    let pnlChart = null;
    let portChart = null;

    function formatMoney(amount, currency='EUR') {
        return new Intl.NumberFormat('es-ES', { style: 'currency', currency: currency }).format(amount);
    }

    function renderYear() {
        const year = document.getElementById('yearSelect').value;
        const data = db[year];
        if (!data) return;

        // KPIs
        document.getElementById('kpi-pnl').innerText = formatMoney(data.total_pnl);
        document.getElementById('kpi-pnl').className = data.total_pnl >= 0 ? 'text-green' : 'text-red';
        
        let divTotal = 0;
        data.dividends.forEach(d => divTotal += (d.gross - d.wht)); // Simplificación suma mixta
        document.getElementById('kpi-divs').innerText = formatMoney(divTotal); // Ojo divisa mixta
        
        document.getElementById('kpi-portfolio').innerText = formatMoney(data.portfolio_value);
        document.getElementById('kpi-fees').innerText = formatMoney(data.fees.trading + data.fees.connectivity);

        // Sales Table
        const salesBody = document.getElementById('sales-body');
        salesBody.innerHTML = '';
        data.sales.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${s.date}</td><td>${s.product}</td><td>${s.qty}</td>
                            <td>${formatMoney(s.sale_net)}</td><td>${formatMoney(s.cost_basis)}</td>
                            <td class="${s.pnl >= 0 ? 'text-green' : 'text-red'}">${formatMoney(s.pnl)}</td>
                            <td>${s.note}</td>`;
            salesBody.appendChild(tr);
        });

        // Divs Table
        const divsBody = document.getElementById('divs-body');
        divsBody.innerHTML = '';
        data.dividends.forEach(d => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${d.date}</td><td>${d.product}</td><td>${d.currency}</td>
                            <td>${d.gross.toFixed(2)}</td><td>${d.wht.toFixed(2)}</td>
                            <td>${(d.gross - d.wht).toFixed(2)}</td>`;
            divsBody.appendChild(tr);
        });

        // Portfolio Table
        const portBody = document.getElementById('portfolio-body');
        portBody.innerHTML = '';
        const labels = [];
        const values = [];
        
        data.portfolio.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${p.name}</td><td>${p.isin}</td><td>${p.qty}</td>
                            <td>${p.avg_price.toFixed(4)}</td><td>${formatMoney(p.total_cost)}</td>`;
            portBody.appendChild(tr);
            
            if(p.total_cost > 0) {
                labels.push(p.name.substring(0,15));
                values.push(p.total_cost);
            }
        });

        // Charts
        if (portChart) portChart.destroy();
        portChart = new Chart(document.getElementById('portfolioChart'), {
            type: 'doughnut',
            data: { labels: labels, datasets: [{ data: values, backgroundColor: ['#4caf50', '#2196f3', '#ff9800', '#f44336', '#9c27b0', '#607d8b'] }] },
            options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#fff' } } } }
        });
        
        // PnL Chart (Static for year view, could be historical)
        if (pnlChart) pnlChart.destroy();
        // Simple bar chart of wins/losses for the year
        const pnlLabels = data.sales.map(s => s.date);
        const pnlData = data.sales.map(s => s.pnl);
        
        pnlChart = new Chart(document.getElementById('pnlChart'), {
            type: 'bar',
            data: { 
                labels: pnlLabels, 
                datasets: [{ 
                    label: 'P&L Operación', 
                    data: pnlData, 
                    backgroundColor: pnlData.map(v => v >= 0 ? '#4caf50' : '#f44336') 
                }] 
            },
            options: { scales: { y: { grid: { color: '#333' } }, x: { grid: { display: false } } }, plugins: { legend: { display: false } } }
        });
    }

    // Init
    const select = document.getElementById('yearSelect');
    Object.keys(db).sort().reverse().forEach(y => {
        const opt = document.createElement('option');
        opt.value = y;
        opt.innerText = y;
        select.appendChild(opt);
    });
    
    // Select latest
    if (select.options.length > 0) {
        select.value = select.options[0].value;
        renderYear();
    }
</script>
</body>
</html>
    """
    with open("DASHBOARD.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n🚀 {Style.CYAN}Web App generada: DASHBOARD.html{Style.RESET}")

def export_all(sales, divs, portfolio, fees, year):
    # 1. CSV Folders
    base_dir = f"informes/{year}"
    os.makedirs(base_dir, exist_ok=True)
    
    # Ventas CSV
    with open(f"{base_dir}/ventas_opas.csv", 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(["FECHA", "PRODUCTO", "ISIN", "CANTIDAD", "V.TRANS", "V.ADQ", "P&L", "NOTAS"])
        for s in sales:
            w.writerow([s['date'], s['product'], s['isin'], 
                        str(s['qty']).replace('.',','), 
                        f"{s['sale_net']:.2f}".replace('.',','), 
                        f"{s['cost_basis']:.2f}".replace('.',','), 
                        f"{s['pnl']:.2f}".replace('.',','), s['note']])
                        
    # Dividendos CSV
    with open(f"{base_dir}/dividendos.csv", 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(["FECHA", "PRODUCTO", "ISIN", "DIVISA", "BRUTO", "RETENCION", "NETO"])
        for (date, isin, prod, curr), d in divs.items():
            w.writerow([date, prod, isin, curr, 
                        f"{d['gross']:.2f}".replace('.',','), 
                        f"{d['wht']:.2f}".replace('.',','), 
                        f"{(d['gross']-d['wht']):.2f}".replace('.',',')])

    # Cartera CSV
    with open(f"{base_dir}/cartera.csv", 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(["PRODUCTO", "ISIN", "CANTIDAD", "PR.MEDIO", "TOTAL INV"])
        grand_total = 0
        for isin, data in portfolio.items():
            qty = sum(b['qty'] for b in data['batches'])
            if qty > 0.001:
                cost = sum(b['qty']*b['unit_cost'] for b in data['batches'])
                grand_total += cost
                w.writerow([data['name'], isin, 
                            str(qty).replace('.',','), 
                            f"{(cost/qty):.4f}".replace('.',','), 
                            f"{cost:.2f}".replace('.',',')])

    print(f"📁 {Style.CYAN}CSVs generados en: {base_dir}/{Style.RESET}")

    # 2. Update JSON DB for Web App
    db_file = "db_fiscal.json"
    if os.path.exists(db_file):
        with open(db_file, 'r', encoding='utf-8') as f:
            full_db = json.load(f)
    else:
        full_db = {}

    # Prepare data structure for JSON
    clean_sales = [{
        'date': s['date'], 'product': s['product'], 'qty': s['qty'],
        'sale_net': s['sale_net'], 'cost_basis': s['cost_basis'], 'pnl': s['pnl'], 'note': s['note']
    } for s in sales]
    
    clean_divs = []
    for (date, isin, prod, curr), d in divs.items():
        clean_divs.append({'date': date, 'product': prod, 'currency': curr, 'gross': d['gross'], 'wht': d['wht']})
        
    clean_port = []
    port_val = 0
    for isin, data in portfolio.items():
        qty = sum(b['qty'] for b in data['batches'])
        if qty > 0.001:
            cost = sum(b['qty']*b['unit_cost'] for b in data['batches'])
            port_val += cost
            clean_port.append({'name': data['name'], 'isin': isin, 'qty': qty, 'avg_price': cost/qty, 'total_cost': cost})

    total_pnl = sum(s['pnl'] for s in sales if not s['blocked'])

    full_db[str(year)] = {
        'sales': clean_sales,
        'dividends': clean_divs,
        'portfolio': clean_port,
        'portfolio_value': port_val,
        'total_pnl': total_pnl,
        'fees': fees
    }

    with open(db_file, 'w', encoding='utf-8') as f:
        json.dump(full_db, f, indent=2)
    
    # Regenerate HTML with updated DB
    generate_web_app(full_db)

def main():
    args = parse_args()
    df_t, df_a = load_data(args.transactions, args.account)
    if df_t.empty: sys.exit("Error: No se cargaron transacciones.")
        
    sales, divs, fees, port, stats = process_portfolio(df_t, df_a, args.year)
    print_report(sales, divs, fees, port, stats, args.year)
    
    if args.report:
        export_all(sales, divs, port, fees, args.year)

if __name__ == "__main__":
    main()