import unittest
import pandas as pd
from datetime import datetime, timedelta
from degiro_app.logic import process_year, load_data_frames, analyze_full_history

class TestAuditDeep(unittest.TestCase):
    
    def test_fee_impact_formula(self):
        """
        AUDITORÍA: Verifica la fórmula de Coste y Valor de Transmisión.
        Norma: 
        - Valor Transmisión = Importe Real Venta - Gastos Venta
        - Valor Adquisición = Importe Real Compra + Gastos Compra
        
        En DEGIRO (CSV):
        - 'Total EUR' en Compra suele ser negativo e incluye el gasto (Precio*Qty + Comision).
        - 'Total EUR' en Venta suele ser positivo (Precio*Qty - Comision).
        
        Validaremos que el sistema respeta esto.
        """
        # Compra: 10 acc a 100€ = 1000€. Comisión 2€. Total CSV: -1002€.
        # Venta: 10 acc a 120€ = 1200€. Comisión 2€. Total CSV: 1198€.
        # PnL Esperado: 1198 - 1002 = 196€.
        
        trans_data = {
            'date': ['01-01-2023', '01-02-2023'],
            'time': ['10:00', '10:00'],
            'product': ['TEST_FEE', 'TEST_FEE'],
            'isin': ['ISIN_FEE', 'ISIN_FEE'],
            'qty': [10.0, -10.0],
            'total_eur': [-1002.0, 1198.0], 
            'fee_eur': [-2.0, -2.0], # Dato informativo en CSV, pero logic usa total_eur
            'date_obj': [pd.to_datetime('2023-01-01'), pd.to_datetime('2023-02-01')]
        }
        df_t = pd.DataFrame(trans_data)
        
        result = process_year(df_t, pd.DataFrame(), 2023)
        sale = result['sales'][0]
        
        print(f"\n[Audit Fee] Net Sale: {sale['sale_net']}, Cost Basis: {sale['cost_basis']}, PnL: {sale['pnl']}")
        
        self.assertEqual(sale['sale_net'], 1198.0)
        self.assertEqual(sale['cost_basis'], 1002.0) # Debe incluir la comisión de compra
        self.assertEqual(sale['pnl'], 196.0)

    def test_precision_rounding(self):
        """
        AUDITORÍA: Verifica la acumulación de errores de coma flotante.
        Sumar muchas fracciones decimales puede dar resultados como 100.000000001.
        La aplicación fiscal debe redondear correctamente.
        """
        # Simulamos 100 compras de 0.1 acciones a 0.1€
        # Coste total esperado: 100 * (0.1 * 0.1) = 1.0€
        qty_list = [0.1] * 100
        total_list = [-0.01] * 100 # 0.1 qty * 0.1 price = 0.01 cost
        
        dates = [pd.to_datetime('2023-01-01')] * 100
        
        # Venta total: 10 acciones.
        qty_list.append(-10.0)
        total_list.append(2.0) # Venta a 0.2€/acc = 2.0€
        dates.append(pd.to_datetime('2023-06-01'))
        
        trans_data = {
            'date': ['01-01-2023'] * 101, # Dummy string
            'time': ['10:00'] * 101,
            'product': ['TEST_PRECISION'] * 101,
            'isin': ['ISIN_PRECISION'] * 101,
            'qty': qty_list,
            'total_eur': total_list,
            'fee_eur': [0.0] * 101,
            'date_obj': dates
        }
        
        df_t = pd.DataFrame(trans_data)
        
        result = process_year(df_t, pd.DataFrame(), 2023)
        sale = result['sales'][0]
        
        print(f"\n[Audit Precision] Cost Basis: {sale['cost_basis']}")
        
        # Validar que no hay deriva tipo 0.99999999997
        self.assertAlmostEqual(sale['cost_basis'], 1.0, places=4)
        self.assertAlmostEqual(sale['pnl'], 1.0, places=4)

    def test_fifo_traceability_long_term(self):
        """
        AUDITORÍA: Integridad FIFO a largo plazo (Trazabilidad).
        Compra en 2018, Venta en 2025. El sistema debe 'recordar' el precio exacto de 2018.
        """
        # 2018: Compra 1 acc a 50.1234€
        # 2019-2024: Años vacíos o con otras operaciones.
        # 2025: Venta 1 acc.
        
        from io import StringIO
        trans_csv = (
            '"Fecha","Hora","Producto","ISIN","Número","Total (EUR)","Costes"\n'
            '"01-01-2018","10:00","LONG_TERM","ISIN_LT","1","-50,1234","0"\n'
            '"01-01-2025","10:00","LONG_TERM","ISIN_LT","-1","100,00","0"\n'
        )
        
        trans_stream = StringIO(trans_csv)
        acc_stream = StringIO("")
        
        history = analyze_full_history(trans_stream, acc_stream)
        
        # Verificar 2025
        data_2025 = history['years'][2025]
        sale = data_2025['sales'][0]
        
        print(f"\n[Audit FIFO] 2018 Cost carried to 2025: {sale['cost_basis']}")
        
        self.assertAlmostEqual(sale['cost_basis'], 50.1234, places=4)
        self.assertEqual(sale['pnl'], 100.0 - 50.1234)

if __name__ == '__main__':
    unittest.main()
