import os
import shutil

# Limpiar entorno previo
if os.path.exists("informes"):
    shutil.rmtree("informes")
if os.path.exists("db_fiscal.json"):
    os.remove("db_fiscal.json")
if os.path.exists("historial_completo.txt"):
    os.remove("historial_completo.txt")

print("🚀 INICIANDO GENERACIÓN DE INFORMES (2018-2025)...")

for year in range(2018, 2026):
    print(f"   ... Procesando {year}")
    
    # Guardar log en texto
    with open("historial_completo.txt", "a") as f:
        f.write(f"\n\n{'='*40}\n REPORTE AÑO {year}\n{'='*40}\n")
    
    # Ejecutar script con flag --report para generar CSVs y actualizar la Web App
    cmd = f"python gestor_fiscal_degiro.py --year {year} --account Account.csv --transactions Transactions.csv --report >> historial_completo.txt"
    os.system(cmd)

print("\n✅ PROCESO COMPLETADO")
print("   📄 Log: historial_completo.txt")
print("   📂 CSVs: carpeta 'informes/'")
print("   🌐 WEB APP: Abre el archivo 'DASHBOARD.html' en tu navegador.")