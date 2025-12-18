import unittest
import pandas as pd
from degiro_app.logic import process_year

class TestSpanishTaxLogic(unittest.TestCase):
    def test_wash_sale_with_old_shares(self):
        """
        Escenario:
        1. 2020: Compra 100 acc a 50€ (Antiguas)
        2. 2023-01-01: Compra 10 acc a 40€ (Nuevas, dentro de ventana)
        3. 2023-01-15: Venta 10 acc a 30€ (Genera pérdida).
        
        Lógica FIFO: Se venden 10 de las de 2020 (Coste 50, Venta 30 -> Pérdida -200).
        Regla 2 meses: Hubo compra el 01-01 (hace 14 días). 
        ¿Quedan acciones de esa compra? Sí, porque FIFO vendió las de 2020.
        Resultado esperado: La pérdida debe bloquearse.
        """
        trans_data = {
            'date': ['01-01-2020', '01-01-2023', '15-01-2023'],
            'time': ['10:00', '10:00', '10:00'],
            'product': ['ACCION', 'ACCION', 'ACCION'],
            'isin': ['ES123456789', 'ES123456789', 'ES123456789'],
            'qty': [100.0, 10.0, -10.0],
            'total_eur': [-5000.0, -400.0, 300.0], # Buy@50, Buy@40, Sell@30
            'fee_eur': [0.0, 0.0, 0.0],
            'date_obj': [pd.to_datetime('2020-01-01'), pd.to_datetime('2023-01-01'), pd.to_datetime('2023-01-15')]
        }
        df_t = pd.DataFrame(trans_data)
        
        # Procesamos 2023
        result = process_year(df_t, pd.DataFrame(), 2023)
        
        sale = result['sales'][0]
        print(f"\nTest Scenario Result: PnL={sale['pnl']}, Blocked={sale['blocked']}")
        
        # Validación: La pérdida (-200) debe estar bloqueada
        self.assertEqual(sale['pnl'], -200.0) 
        self.assertTrue(sale['blocked'], "La pérdida debería bloquearse porque se compraron acciones homogéneas 15 días antes y permanecen en cartera.")

if __name__ == '__main__':
    unittest.main()
