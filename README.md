# 🤖 Gestor Fiscal Degiro (FIFO + Tax Harvesting)

Herramienta en Python para automatizar el cálculo de impuestos (P&L Realizado) y el seguimiento de cartera (P&L Latente) utilizando exportaciones CSV de Degiro.

El script aplica el método **FIFO** (First-In, First-Out) y se conecta a **Yahoo Finance** para obtener precios en tiempo real y tipos de cambio de divisas.

## 🚀 Características

* **Cálculo Fiscal FIFO:** Cumple con el criterio estándar (las primeras acciones compradas son las primeras en venderse).
* **Gestión de Comisiones:** Las comisiones de compra/venta se integran en el coste base (reduciendo la plusvalía fiscal), según normativa común.
* **Multidivisa:** Conversión automática de P&L y precios a **EUR** (soporta USD, JPY, GBP, etc.).
* **Detección Automática de Tickers:** Convierte ISINs a Tickers de Yahoo Finance automáticamente.
* **Reportes en Consola:**
  * 📋 **Fiscal:** Ganancias y pérdidas cerradas en el año fiscal seleccionado.
  * 📊 **Cartera Viva:** Estado actual de tus posiciones abiertas con rentabilidad latente actualizada.

## 📋 Requisitos

* Python 3.8 o superior.
* Librerías externas (ver instalación).

## ⚙️ Instalación

1. Clona este repositorio o descarga el script.
2. Instala las dependencias necesarias:

    pip install pandas requests yfinance

## 📂 Exportación de Datos (Degiro)

Para que el script funcione, necesitas los archivos CSV de tu cuenta:

1. Entra en Degiro.
2. Ve a **Estado de Cuenta** (o Informes).
3. Selecciona un rango de fechas (recomendado: **Desde el inicio de tu cuenta** hasta hoy para asegurar que el FIFO es correcto).
4. Exporta como **CSV** (formato Español, donde los decimales son `,`).
5. Guarda el archivo (o archivos) en una carpeta.

> **Nota:** El script soporta múltiples archivos CSV (histórico). Si tienes varios años en archivos separados, guárdalos todos en la misma carpeta; el script los unirá y ordenará cronológicamente.

## 💻 Uso

Ejecuta el script desde la terminal:

    python gestor_fiscal_degiro.py [opciones]

### Ejemplos

**1. Uso básico (busca CSVs en la carpeta actual y calcula el año presente):**

    python gestor_fiscal_degiro.py

**2. Calcular impuestos para el año 2023:**

    python gestor_fiscal_degiro.py --year 2023

**3. Indicar una carpeta específica donde están los CSV:**

    python gestor_fiscal_degiro.py --dir "./mis_datos_degiro"

**4. Ordenar la cartera viva por porcentaje de rentabilidad (ascendente):**

    python gestor_fiscal_degiro.py --sort percent --asc

## 🔧 Argumentos Disponibles

| Argumento | Descripción | Default |
| :--- | :--- | :--- |
| `--dir` | Directorio donde se encuentran los archivos `.csv`. | `.` (Directorio actual) |
| `--year` | Año fiscal objetivo para el reporte de P&L Realizado. | Último año detectado |
| `--sort` | Criterio para ordenar la tabla de cartera viva (`pnl`, `percent`, `name`, `qty`). | `pnl` |
| `--asc` | Bandera para ordenar de forma ascendente (menor a mayor). | False (Descendente) |

## 🛠️ Configuración Avanzada (ISINs Manuales)

A veces, la API de Yahoo Finance no encuentra un ISIN específico (común en fondos raros o acciones muy recientes).
Puedes editar el diccionario `ISIN_MANUAL_MAP` al inicio del script.

## ⚠️ Disclaimer

Este software se distribuye "tal cual" sin garantías de ningún tipo.
- **No soy asesor fiscal.** - Los cálculos son aproximaciones basadas en los datos exportados y el método FIFO.
- Verifica siempre los resultados con los informes oficiales de tu broker y tu asesor fiscal antes de presentar impuestos.