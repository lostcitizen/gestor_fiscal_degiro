from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
from logic import analyze_full_history

app = Flask(__name__)
app.secret_key = 'secreto_fiscal'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Cache en memoria simple
DB_CACHE = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'account' not in request.files or 'transactions' not in request.files: return "Faltan archivos", 400
        
        acc = request.files['account']
        trans = request.files['transactions']
        
        acc_path = os.path.join(UPLOAD_FOLDER, 'Account.csv')
        trans_path = os.path.join(UPLOAD_FOLDER, 'Transactions.csv')
        acc.save(acc_path)
        trans.save(trans_path)

        # Analizar TODO
        full_data = analyze_full_history(trans_path, acc_path)
        DB_CACHE['data'] = full_data
        
        return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'data' not in DB_CACHE: return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/api/data')
def get_data():
    return jsonify(DB_CACHE.get('data', {}))

if __name__ == '__main__':
    app.run(debug=True, port=5000)