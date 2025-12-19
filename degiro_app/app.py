import os
import io
import csv
import zipfile
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from .logic import load_data_frames, analyze_full_history
from degiro_app.config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Directorio persistente
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

PATH_ACC = os.path.join(DATA_DIR, 'Account.csv')
PATH_TRANS = os.path.join(DATA_DIR, 'Transactions.csv')

# Base de datos en memoria (Cache)
DB_CACHE = {}

def process_files_from_disk():
    """Carga y procesa los archivos desde el disco."""
    try:
        if not os.path.exists(PATH_ACC) or not os.path.exists(PATH_TRANS):
            return False
            
        with open(PATH_TRANS, 'r', encoding='utf-8') as ft, \
             open(PATH_ACC, 'r', encoding='utf-8') as fa:
             
            # Cargar en streams para no cambiar la firma de logic
            # Aunque analyze_full_history ya acepta file objects, así que ft/fa sirven directo.
            full_data = analyze_full_history(ft, fa)
            
            if not full_data or 'global' not in full_data: 
                print("Error: Datos procesados vacíos o estructura inválida.")
                return False
                
            DB_CACHE['data'] = full_data
            return True
    except Exception as e:
        print(f"Error procesando archivos persistentes: {e}")
        return False

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'account' not in request.files or 'transactions' not in request.files:
            return "Faltan archivos", 400
        
        acc_file = request.files['account']
        trans_file = request.files['transactions']
        
        # Guardar en disco (sobrescribir)
        acc_file.save(PATH_ACC)
        trans_file.save(PATH_TRANS)

        # Procesar
        if process_files_from_disk():
            return redirect(url_for('dashboard'))
        else:
            return "Error procesando los archivos subidos. Verifique el formato.", 400

    # GET: Verificar si ya existen datos
    if 'data' in DB_CACHE:
        return redirect(url_for('dashboard'))
    
    # Intentar cargar desde disco si se reinició el servidor
    if process_files_from_disk():
        return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'data' not in DB_CACHE:
        # Intento de último recurso si se accede directo
        if process_files_from_disk():
            return render_template('dashboard.html')
        return redirect(url_for('index'))
        
    return render_template('dashboard.html')

@app.route('/reset')
def reset_data():
    """Borra los datos en memoria y disco."""
    DB_CACHE.clear()
    if os.path.exists(PATH_ACC): os.remove(PATH_ACC)
    if os.path.exists(PATH_TRANS): os.remove(PATH_TRANS)
    return redirect(url_for('index'))

@app.route('/api/data')
def get_data():
    return jsonify(DB_CACHE.get('data', {}))

# --- NUEVA RUTA PARA DESCARGAR ZIP ---
@app.route('/download/<int:year>')
def download_report(year):
    if 'data' not in DB_CACHE or year not in DB_CACHE['data']['years']:
        return "Datos no encontrados para este año", 404

    data = DB_CACHE['data']['years'][year]
    
    # Crear buffer en memoria para el ZIP
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        
        # Función auxiliar para escribir CSV
        def add_csv_to_zip(filename, headers, rows):
            si = io.StringIO()
            # Excel europeo usa ; como separador y codificación utf-8-sig
            cw = csv.writer(si, delimiter=';')
            cw.writerow(headers)
            cw.writerows(rows)
            zip_file.writestr(filename, si.getvalue().encode('utf-8-sig'))

        # 1. COMPRAS.csv
        rows_buys = []
        for b in data['purchases']:
            rows_buys.append([
                b['date'], b['product'], b['isin'],
                fmt_num(b['qty']), fmt_num(b['price']), fmt_num(b['total']), fmt_num(b['fee'])
            ])
        add_csv_to_zip(f"compras_{year}.csv", 
                      ["FECHA", "PRODUCTO", "ISIN", "CANTIDAD", "PRECIO", "TOTAL", "COMISION"], 
                      rows_buys)

        # 2. VENTAS.csv
        rows_sales = []
        for s in data['sales']:
            rows_sales.append([
                s['date'], s['product'], s['isin'],
                fmt_num(s['qty']), fmt_num(s['sale_net']), fmt_num(s['cost_basis']), 
                fmt_num(s['pnl']), s['note']
            ])
        add_csv_to_zip(f"ventas_opas_{year}.csv", 
                      ["FECHA", "PRODUCTO", "ISIN", "CANTIDAD", "VALOR TRANSMISION", "VALOR ADQUISICION", "P&L NETO", "NOTAS"], 
                      rows_sales)

        # 3. DIVIDENDOS.csv
        rows_divs = []
        for d in data['dividends']:
            rows_divs.append([
                d['date'], d['product'], d['isin'], d['currency'],
                fmt_num(d['gross']), fmt_num(d['wht']), fmt_num(d['net'])
            ])
        add_csv_to_zip(f"dividendos_{year}.csv", 
                      ["FECHA", "PRODUCTO", "ISIN", "DIVISA", "BRUTO", "RETENCION", "NETO"], 
                      rows_divs)

        # 4. CARTERA.csv
        rows_port = []
        for p in data['portfolio']:
            rows_port.append([
                p['name'], p['isin'], fmt_num(p['qty']), 
                fmt_num(p['avg_price']), fmt_num(p['total_cost'])
            ])
        add_csv_to_zip(f"cartera_fin_{year}.csv", 
                      ["PRODUCTO", "ISIN", "CANTIDAD", "PRECIO MEDIO", "TOTAL INVERTIDO"], 
                      rows_port)

    # Preparar respuesta
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'Informe_Fiscal_DEGIRO_{year}.zip'
    )

def fmt_num(val):
    """Convierte float a string formato europeo (coma decimal)"""
    if val is None: return "0,00"
    return f"{val:.2f}".replace('.', ',')

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
