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

1.  **Desde el Código Fuente (Desarrollo):**
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

2.  **Desde el Paquete de Release (.tar.gz):**
    Si has descargado un paquete `gestor_fiscal_degiro-vX.Y.Z.tar.gz` de la sección Releases:
    1. Descomprime el archivo.
    2. Dentro, encontrarás la estructura del repositorio. Puedes usar los scripts y comandos como si hubieras clonado el repositorio.
    3. Para ejecutar de forma nativa: `FLASK_APP=degiro_app.app FLASK_DEBUG=0 flask run`
    4. Para ejecutar con Docker `./scripts/degiroctl start`

3.  **Acceder a la aplicación:**
    Abre tu navegador y ve a `http://127.0.0.1:5000`.

4.  **Cargar datos:**
    - La primera vez, se te pedirá subir tus archivos `Account.csv` y `Transactions.csv`.
    - **Importante:** Para una precisión fiscal completa (cálculo FIFO correcto), asegúrate de descargar el **historial completo** de transacciones desde DEGIRO.
    - La aplicación guardará los archivos localmente en `./degiro_app/data`. La próxima vez que arranques, cargará los datos automáticamente.

5.  **Actualizar datos (año siguiente):**
    - Descarga de DEGIRO los nuevos archivos CSV con el historial completo actualizado.
    - En el dashboard de la aplicación, haz clic en el icono de "subir" (<i class="bi bi-upload"></i>) en la barra de navegación. Esto borrará los datos antiguos y te llevará a la pantalla de carga para que puedas subir los nuevos.

## Ejecutar con Docker

Hemos preparado un script `degiroctl` para gestionar la aplicación fácilmente con Docker. Este script se encuentra en la carpeta `scripts/`.

1.  **Asegúrate de tener Docker instalado.**

2.  **Uso del script `degiroctl`:**
    Desde la raíz del proyecto (ya sea el repositorio clonado o el paquete de release descomprimido), puedes usar los siguientes comandos:

    *   **Iniciar la aplicación (construye imagen si es necesario y ejecuta el contenedor):**
        ```bash
        ./scripts/degiroctl start
        ```
        Accede a la aplicación en `http://localhost:5000`.

    *   **Construir solo la imagen Docker:**
        ```bash
        ./scripts/degiroctl build
        ```

    *   **Detener el contenedor:**
        ```bash
        ./scripts/degiroctl stop
        ```

    *   **Reiniciar el contenedor:**
        ```bash
        ./scripts/degiroctl restart
        ```

    *   **Eliminar el contenedor:**
        ```bash
        ./scripts/degiroctl rm
        ```

    *   **Reconstruir la imagen y reiniciar el contenedor:**
        ```bash
        ./scripts/degiroctl rebuild
        ```

    *   **Ver los logs del contenedor:**
        ```bash
        ./scripts/degiroctl logs
        ```

    *   **Ver el estado del contenedor:**
        ```bash
        ./scripts/degiroctl status
        ```

    *   **Ayuda:**
        ```bash
        ./scripts/degiroctl help
        ```

    *   **Persistencia:** Tus datos se guardarán en la carpeta `./degiro_app/data` en la raíz de tu proyecto.

## Desarrollo

Si quieres contribuir al desarrollo, aquí tienes las guías para ejecutar el entorno de pruebas.

1.  Haz un Fork del proyecto.
2.  Crea una nueva rama para tu funcionalidad (`git checkout -b feature/AmazingFeature`).
3.  Realiza tus cambios y haz commit (`git commit -m 'Add some AmazingFeature'`).
4.  Empuja tus cambios a la rama (`git push origin feature/AmazingFeature`).
5.  Abre una Pull Request.

Asegúrate de que tus cambios respetan la arquitectura existente y, si es posible, añade tests para validar tu nueva funcionalidad.

## Licencia

Este proyecto está distribuido bajo la **Licencia MIT**. Consulta el archivo `LICENSE` para más detalles.
