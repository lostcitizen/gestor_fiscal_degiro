# Gestor Fiscal para DEGIRO (España)

[![CI Build Status](https://github.com/lostcitizen/gestor_fiscal_degiro/actions/workflows/ci.yml/badge.svg)](https://github.com/lostcitizen/gestor_fiscal_degiro/actions/workflows/ci.yml)
[![Code Coverage](https://codecov.io/gh/lostcitizen/gestor_fiscal_degiro/branch/main/graph/badge.svg)](https://codecov.io/gh/lostcitizen/gestor_fiscal_degiro)
[![Latest Release](https://img.shields.io/github/v/release/lostcitizen/gestor_fiscal_degiro)](https://github.com/lostcitizen/gestor_fiscal_degiro/releases)

Este proyecto es una aplicación web Flask diseñada para procesar los informes CSV de DEGIRO (`Account.csv` y `Transactions.csv`) y generar un análisis fiscal detallado, optimizado para la declaración de la renta en España.

La aplicación calcula automáticamente ganancias y pérdidas patrimoniales usando el método **FIFO**, aplica la **norma anti-aplicación de los 2 meses** (wash sale rule), y consolida los dividendos y comisiones para ofrecer una visión clara de la situación fiscal anual.

## Características

- **Dashboard Interactivo:** Visualiza P&L fiscal vs. real, dividendos, comisiones y evolución de la cartera.
- **Cálculo FIFO Automático:** Traza el coste de adquisición de cada venta de forma precisa.
- **Regla Anti-aplicación (2 Meses):** Detecta y bloquea automáticamente pérdidas no deducibles por recompra, mostrando su estado (Activo, Liberado, Riesgo).
- **Consolidación de Dividendos:** Agrupa dividendos y retenciones para un reporte neto claro.
- **Procesamiento 100% Local:** Tus datos nunca salen de tu ordenador, garantizando total privacidad.
- **Persistencia de Datos:** Sube tus archivos una vez y la aplicación los recordará.

## Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone https://github.com/tu_usuario/gestor_fiscal_degiro.git
    cd gestor_fiscal_degiro
    ```

2.  **Crear un entorno virtual (recomendado):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # En Windows: venv\Scripts\activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

## Uso

1.  **Ejecutar la aplicación:**
    Desde la raíz del proyecto, ejecuta el siguiente comando:
    ```bash
    export FLASK_APP=degiro_app/app.py
    export FLASK_DEBUG=1
    flask run
    ```
    *En Windows (PowerShell):*
    ```powershell
    $env:FLASK_APP = "degiro_app/app.py"
    $env:FLASK_DEBUG = "1"
    flask run
    ```

2.  **Acceder a la aplicación:**
    Abre tu navegador y ve a `http://127.0.0.1:5000`.

3.  **Cargar datos:**
    - La primera vez, se te pedirá subir tus archivos `Account.csv` y `Transactions.csv`.
    - **Importante:** Para una precisión fiscal completa (cálculo FIFO correcto), asegúrate de descargar el **historial completo** de transacciones desde DEGIRO.
    - La aplicación guardará los archivos localmente. La próxima vez que arranques, cargará los datos automáticamente.

4.  **Actualizar datos (año siguiente):**
    - Descarga de DEGIRO los nuevos archivos CSV con el historial completo actualizado.
    - En el dashboard de la aplicación, haz clic en el icono de "subir" (<i class="bi bi-upload"></i>) en la barra de navegación. Esto borrará los datos antiguos y te llevará a la pantalla de carga para que puedas subir los nuevos.

## Desarrollo

Si quieres contribuir al desarrollo, aquí tienes las guías para ejecutar el entorno de pruebas.

### Dependencias de Desarrollo

Instala las dependencias adicionales para testing y cobertura:
```bash
pip install -r requirements-dev.txt
```

### Ejecutar Tests

Para ejecutar la suite completa de tests, usa `pytest`:
```bash
pytest
```

### Análisis de Cobertura

Para generar un informe de cobertura de código en la terminal:
```bash
pytest --cov=degiro_app tests/
```

## Contribución

¡Las contribuciones son bienvenidas! Si quieres mejorar el proyecto, por favor sigue estos pasos:

1.  Haz un Fork del proyecto.
2.  Crea una nueva rama para tu funcionalidad (`git checkout -b feature/AmazingFeature`).
3.  Realiza tus cambios y haz commit (`git commit -m 'Add some AmazingFeature'`).
4.  Empuja tus cambios a la rama (`git push origin feature/AmazingFeature`).
5.  Abre una Pull Request.

Asegúrate de que tus cambios respetan la arquitectura existente y, si es posible, añade tests para validar tu nueva funcionalidad.

## Licencia

Este proyecto está distribuido bajo la **Licencia MIT**. Consulta el archivo `LICENSE` para más detalles.
