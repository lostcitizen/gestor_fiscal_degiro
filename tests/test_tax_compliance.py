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

    def test_blocked_status_dates(self):
        """
        Verifica que blocked_status ('active' vs 'released') y unlock_date se calculen correctamente.
        """
        from datetime import datetime, timedelta
        today = datetime.now()
        
        # Caso 1: Bloqueo Histórico (Venta hace 1 año)
        date_past = today - timedelta(days=400)
        date_past_str = date_past.strftime('%d-%m-%Y')
        date_rebuy_past = (date_past + timedelta(days=10)).strftime('%d-%m-%Y')
        
        # Caso 2: Bloqueo Activo (Venta ayer)
        date_recent = today - timedelta(days=1)
        date_recent_str = date_recent.strftime('%d-%m-%Y')
        date_rebuy_recent = (date_recent + timedelta(days=10)).strftime('%d-%m-%Y')
        
        trans_data = {
            'date': [date_past_str, date_rebuy_past, date_recent_str, date_rebuy_recent],
            'time': ['10:00', '11:00', '10:00', '11:00'],
            'product': ['OLD', 'OLD', 'NEW', 'NEW'],
            'isin': ['ISIN1', 'ISIN1', 'ISIN2', 'ISIN2'],
            'qty': [-10.0, 10.0, -10.0, 10.0], # Venta seguida de recompra (Wash Sale clásica)
            'total_eur': [50.0, -60.0, 50.0, -60.0], # Venta a 50, Recompra a 60 (Asumimos coste base mayor para generar perdida)
            # Para que sea perdida, necesitamos coste base > 50.
            # Como no hay compra inicial, el sistema asumirá coste 0 -> ganancia -> NO BLOQUEO.
            # Necesitamos compras iniciales.
            'fee_eur': [0,0,0,0],
            'date_obj': [date_past, date_past + timedelta(days=10), date_recent, date_recent + timedelta(days=10)]
        }
        
        # Añadimos compras iniciales antiguas para generar coste base
        initial_buy_date = date_past - timedelta(days=100)
        trans_data_complete = {
            'date': [initial_buy_date.strftime('%d-%m-%Y')] * 2 + trans_data['date'],
            'time': ['09:00'] * 2 + trans_data['time'],
            'product': ['OLD', 'NEW'] + trans_data['product'],
            'isin': ['ISIN1', 'ISIN2'] + trans_data['isin'],
            'qty': [10.0, 10.0] + trans_data['qty'],
            'total_eur': [-100.0, -100.0] + trans_data['total_eur'], # Coste 100. Venta 50 -> Pérdida 50.
            'fee_eur': [0.0, 0.0] + trans_data['fee_eur'],
            'date_obj': [initial_buy_date, initial_buy_date] + trans_data['date_obj']
        }
        
        df_t = pd.DataFrame(trans_data_complete)
        
        # Procesar años. Como las fechas son relativas a hoy, pueden caer en distintos años.
        # Simplemente procesamos el año de la fecha 'today'.
        target_year = today.year
        # Si date_past cae en año anterior, puede que necesitemos procesar ese año también si queremos verlo en sales.
        # Pero process_year solo devuelve lo del target_year.
        # Truco: forzar que todo ocurra en el target_year para el test, o procesar ambos.
        
        # Mejor estrategia: Validar solo la lógica de fechas, asumiendo que caen en el mismo año 
        # o iterar los años relevantes.
        
        # Si today es 1 de Enero, date_recent (ayer) es año anterior.
        # Vamos a asegurar fechas dentro del mismo "proceso" lógico modificando el dataframe directamente?
        # No, mejor procesamos el año de la transacción específica.
        
        year_past = date_past.year
        result_past = process_year(df_t, pd.DataFrame(), year_past)
        sale_old = [s for s in result_past['sales'] if s['product'] == 'OLD'][0]
        
        year_recent = date_recent.year
        # Si es diferente año, procesamos de nuevo con el dataframe completo (no importa redundancia)
        result_recent = process_year(df_t, pd.DataFrame(), year_recent)
        sale_new = [s for s in result_recent['sales'] if s['product'] == 'NEW'][0]
        
        # Validación OLD (Released)
        print(f"\nOLD Sale: {sale_old['unlock_date']} Status: {sale_old['blocked_status']}")
        self.assertTrue(sale_old['blocked'])
        self.assertEqual(sale_old['blocked_status'], 'released')
        expected_unlock_old = (date_past + timedelta(days=62)).strftime('%d-%m-%Y')
        self.assertEqual(sale_old['unlock_date'], expected_unlock_old)

        # Validación NEW (Active)
        print(f"NEW Sale: {sale_new['unlock_date']} Status: {sale_new['blocked_status']}")
        self.assertTrue(sale_new['blocked'])
        self.assertEqual(sale_new['blocked_status'], 'active')
        expected_unlock_new = (date_recent + timedelta(days=62)).strftime('%d-%m-%Y')
        self.assertEqual(sale_new['unlock_date'], expected_unlock_new)

    def test_wash_sale_risk_warning(self):
        """
        Verifica que una pérdida reciente NO bloqueada active la advertencia de 'Riesgo de Recompra'.
        """
        from datetime import datetime, timedelta
        today = datetime.now()
        
        # Venta ayer con pérdida, sin compras previas conflictivas
        date_sale = today - timedelta(days=1)
        date_sale_str = date_sale.strftime('%d-%m-%Y')
        
        # Compra antigua (hace 1 año) para establecer coste base alto
        date_buy = today - timedelta(days=365)
        date_buy_str = date_buy.strftime('%d-%m-%Y')
        
        trans_data = {
            'date': [date_buy_str, date_sale_str],
            'time': ['10:00', '10:00'],
            'product': ['RISK_TEST', 'RISK_TEST'],
            'isin': ['ISIN_RISK', 'ISIN_RISK'],
            'qty': [10.0, -10.0],
            'total_eur': [-1000.0, 500.0], # Coste 1000, Venta 500 -> Pérdida -500
            'fee_eur': [0,0],
            'date_obj': [date_buy, date_sale]
        }
        
        df_t = pd.DataFrame(trans_data)
        
        result = process_year(df_t, pd.DataFrame(), today.year)
        sale = result['sales'][0]
        
        print(f"\nRisk Test: PnL={sale['pnl']}, Blocked={sale['blocked']}, Risk={sale.get('wash_sale_risk')}")
        
        self.assertEqual(sale['pnl'], -500.0)
        self.assertFalse(sale['blocked'], "No debería estar bloqueada (no hay recompras).")
        self.assertTrue(sale['wash_sale_risk'], "Debería marcar riesgo de wash sale por ser reciente.")
        
        expected_safe_date = (date_sale + timedelta(days=62)).strftime('%d-%m-%Y')
        self.assertEqual(sale['repurchase_safe_date'], expected_safe_date)

    def test_loss_consolidated_historical(self):
        """
        Verifica que una pérdida antigua sin problemas se marque como 'loss_consolidated'.
        """
        from datetime import datetime, timedelta
        
        # Venta hace 2 años con pérdida, sin recompras
        date_sale = datetime.now() - timedelta(days=730)
        date_buy = date_sale - timedelta(days=30)
        
        trans_data = {
            'date': [date_buy.strftime('%d-%m-%Y'), date_sale.strftime('%d-%m-%Y')],
            'time': ['10:00', '10:00'],
            'product': ['OLD_CLEAN', 'OLD_CLEAN'],
            'isin': ['ISIN_CLEAN', 'ISIN_CLEAN'],
            'qty': [10.0, -10.0],
            'total_eur': [-1000.0, 800.0], # Pérdida -200
            'fee_eur': [0,0],
            'date_obj': [date_buy, date_sale]
        }
        
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), date_sale.year)
        sale = result['sales'][0]
        
        print(f"\nConsolidated Test: PnL={sale['pnl']}, Consolidated={sale.get('loss_consolidated')}")
        
        self.assertFalse(sale['blocked'])
        self.assertFalse(sale['wash_sale_risk'])
        self.assertTrue(sale['loss_consolidated'], "Debería estar consolidada por ser antigua y sin recompras.")

if __name__ == '__main__':
    unittest.main()
