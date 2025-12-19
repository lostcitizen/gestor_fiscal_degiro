import pytest
import os
import pandas as pd
from degiro_app.app import app as flask_app
from degiro_app.app import DB_CACHE, PATH_ACC, PATH_TRANS
from io import BytesIO

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Seteamos la app en modo testing
    flask_app.config.update({
        "TESTING": True,
    })

    # Limpiamos el cache y los archivos persistentes antes de cada test
    DB_CACHE.clear()
    if os.path.exists(PATH_ACC): os.remove(PATH_ACC)
    if os.path.exists(PATH_TRANS): os.remove(PATH_TRANS)

    yield flask_app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

def test_index_get(client):
    """Test GET / returns 200 and the upload form."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Sube tus archivos de DEGIRO" in response.data

def test_index_post_success(client):
    """Test POST / with valid files redirects and populates cache."""
    trans_csv = b'"Fecha","Hora","Producto","ISIN","N\xc3\xbamero","Total (EUR)","Costes de transacci\xc3\xb3n (EUR)"\n"05-01-2023","10:00","PRODUCT_A","ISIN_A","10.0","-100.0","-1.0"\n'
    acc_csv = b'"Fecha","Producto","ISIN","Descripci\xc3\xb3n","Variaci\xc3\xb3n"\n"20-03-2023","PRODUCT_A","ISIN_A","Dividendo","EUR 10,00"\n'
    
    data = {
        'transactions': (BytesIO(trans_csv), 'transactions.csv'),
        'account': (BytesIO(acc_csv), 'account.csv')
    }
    
    response = client.post('/', data=data, content_type='multipart/form-data')
    
    assert response.status_code == 302 # Redirect
    assert response.headers['Location'] == '/dashboard'
    assert 'data' in DB_CACHE
    assert 'global' in DB_CACHE['data']
    assert 'years' in DB_CACHE['data']

def test_index_post_missing_files(client):
    """Test POST / with a missing file returns 400."""
    trans_csv = b'"Fecha","Hora","Producto","ISIN","N\xc3\xbamero","Total (EUR)","Costes de transacci\xc3\xb3n (EUR)"\n"05-01-2023","10:00","PRODUCT_A","ISIN_A","10.0","-100.0","-1.0"\n'
    data = {
        'transactions': (BytesIO(trans_csv), 'transactions.csv'),
    }
    response = client.post('/', data=data, content_type='multipart/form-data')
    assert response.status_code == 400

def test_dashboard_redirect_no_data(client):
    """Test GET /dashboard redirects to / when cache is empty."""
    response = client.get('/dashboard')
    assert response.status_code == 302
    assert response.headers['Location'] == '/'

def test_download_report_no_data(client):
    """Test GET /download/<year> returns 404 when cache is empty."""
    response = client.get('/download/2023')
    assert response.status_code == 404

def test_index_post_processing_error(client, mocker):
    """Test POSTing files that cause a backend processing error."""
    # Mockear la función de procesamiento para que falle
    mocker.patch('degiro_app.app.process_files_from_disk', return_value=False)
    
    data = {
        'transactions': (BytesIO(b'corrupt'), 'transactions.csv'),
        'account': (BytesIO(b'corrupt'), 'account.csv')
    }
    
    response = client.post('/', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    assert b"Error procesando los archivos" in response.data

def test_dashboard_last_resort_redirect(client):
    """
    Test GET /dashboard with empty cache and no files on disk.
    It should try to load, fail, and redirect.
    """
    # El fixture 'app' ya se encarga de que no haya nada en cache ni disco
    response = client.get('/dashboard')
    assert response.status_code == 302
    assert response.headers['Location'] == '/'
def test_download_report_invalid_year(client):
    """Test downloading a report for a year that does not exist."""
    # Subir datos válidos primero para que haya cache
    trans_csv = b'"Fecha","Hora","Producto","ISIN","N\xc3\xbamero","Total (EUR)"\n"05-01-2023","10:00","A","B","1","-10"\n'
    acc_csv = b''
    data = {
        'transactions': (BytesIO(trans_csv), 'transactions.csv'),
        'account': (BytesIO(acc_csv), 'account.csv')
    }
    client.post('/', data=data)
    
    # Pedir un año que no está en los datos
    response = client.get('/download/2099')
    assert response.status_code == 404
    assert b"Datos no encontrados" in response.data

def test_index_post_empty_or_invalid_files(client, mocker):
    """
    Test POST / with files that are empty or have invalid format,
    causing load_data_frames to return empty DataFrames.
    """
    # Mock load_data_frames to return empty DataFrames
    mocker.patch('degiro_app.logic.load_data_frames', return_value=(pd.DataFrame(), pd.DataFrame()))
    
    # Simulate uploading valid-looking but empty files
    trans_csv = b'Header\n'
    acc_csv = b'Header\n'
    data = {
        'transactions': (BytesIO(trans_csv), 'transactions.csv'),
        'account': (BytesIO(acc_csv), 'account.csv')
    }
    
    response = client.post('/', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    assert b"Error procesando los archivos" in response.data


def test_full_flow(client):
    """
    Tests the full user flow:
    1. POST files to /
    2. GET /dashboard
    3. GET /api/data
    4. GET /download/<year>
    """
    # 1. Upload files
    trans_csv = b'"Fecha","Hora","Producto","ISIN","N\xc3\xbamero","Total (EUR)","Costes de transacci\xc3\xb3n (EUR)"\n"05-01-2023","10:00","PRODUCT_A","ISIN_A","10.0","-100.0","-1.0"\n'
    acc_csv = b'"Fecha","Producto","ISIN","Descripci\xc3\xb3n","Variaci\xc3\xb3n"\n"20-03-2023","PRODUCT_A","ISIN_A","Dividendo","EUR 10,00"\n'
    data = {
        'transactions': (BytesIO(trans_csv), 'transactions.csv'),
        'account': (BytesIO(acc_csv), 'account.csv')
    }
    client.post('/', data=data, content_type='multipart/form-data')
    
    # 2. Test Dashboard
    response_dash = client.get('/dashboard')
    assert response_dash.status_code == 200
    assert b"Resumen Hist" in response_dash.data # Check for a keyword from the dashboard

    # 3. Test API
    response_api = client.get('/api/data')
    assert response_api.status_code == 200
    json_data = response_api.get_json()
    assert 'global' in json_data
    assert json_data['global']['total_divs_net'] == 10.0

    # 4. Test Download
    response_download = client.get('/download/2023')
    assert response_download.status_code == 200
    assert response_download.mimetype == 'application/zip'
    assert 'Informe_Fiscal_DEGIRO_2023.zip' in response_download.headers['Content-Disposition']

    # Verify zip content
    import zipfile
    with zipfile.ZipFile(BytesIO(response_download.data)) as z:
        assert 'ventas_opas_2023.csv' in z.namelist()
        assert 'dividendos_2023.csv' in z.namelist()

if __name__ == '__main__':
    pytest.main()
