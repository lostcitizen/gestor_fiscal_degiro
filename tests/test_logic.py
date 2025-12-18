import unittest
import pandas as pd
from io import StringIO
from datetime import datetime
from degiro_app.logic import clean_number, load_data_frames, process_year

class TestLogic(unittest.TestCase):

    def test_clean_number(self):
        """Tests the clean_number function with various string formats."""
        self.assertEqual(clean_number("1.234,56"), 1234.56)
        self.assertEqual(clean_number("1,234.56"), 1234.56)
        self.assertEqual(clean_number("1.234"), 1234.0)
        self.assertEqual(clean_number("1,23"), 1.23)
        self.assertEqual(clean_number("-50.00"), -50.0)
        self.assertEqual(clean_number("  25.5  "), 25.5)
        self.assertEqual(clean_number('"100"'), 100.0)
        self.assertEqual(clean_number(""), 0.0)
        self.assertEqual(clean_number(None), 0.0)
        self.assertEqual(clean_number(pd.NA), 0.0)
        self.assertEqual(clean_number("abc"), 0.0)
        self.assertEqual(clean_number("EUR 1.000,00"), 1000.0)

    def test_load_data_frames(self):
        """Tests loading data from CSV streams."""
        trans_csv = (
            '"Fecha","Hora","Producto","ISIN","Número","Total (EUR)","Costes de transacción (EUR)"\n'
            '"25-05-2023","15:30","BUY TESLA","US88160R1014","10.0","-1000.50","-1.00"\n'
        )
        acc_csv = (
            '"Fecha","Producto","ISIN","Descripción","Variación"\n'
            '"10-06-2023","TESLA","US88160R1014","Dividendo","EUR 50,25"\n'
        )
        
        trans_stream = StringIO(trans_csv)
        acc_stream = StringIO(acc_csv)
        
        df_t, df_a = load_data_frames(trans_stream, acc_stream)
        
        # Test transactions DataFrame
        self.assertEqual(len(df_t), 1)
        self.assertEqual(df_t.iloc[0]['product'], "BUY TESLA")
        self.assertEqual(df_t.iloc[0]['qty'], 10.0)
        self.assertEqual(df_t.iloc[0]['total_eur'], -1000.50)
        self.assertEqual(df_t.iloc[0]['fee_eur'], -1.00)
        self.assertEqual(df_t.iloc[0]['date_obj'], pd.to_datetime("2023-05-25"))
        
        # Test account DataFrame
        self.assertEqual(len(df_a), 1)
        self.assertEqual(df_a.iloc[0]['product'], "TESLA")
        self.assertEqual(df_a.iloc[0]['desc'], "Dividendo")
        self.assertEqual(df_a.iloc[0]['amount_fix'], 50.25)

        # Test with empty files
        df_t_empty, df_a_empty = load_data_frames(StringIO(""), StringIO(""))
        self.assertTrue(df_t_empty.empty)
        self.assertTrue(df_a_empty.empty)

        # Test with malformed files
        df_t_malformed, df_a_malformed = load_data_frames(StringIO("a,b,c\n1,2"), StringIO("d,e\n3"))
        self.assertTrue(df_t_malformed.empty) # Should fail to parse and return empty
        self.assertTrue(df_a_malformed.empty)

    def test_process_year(self):
        """Tests the main process_year logic with a sample set of transactions."""
        trans_data = {
            'date': ['05-01-2023', '15-06-2023'],
            'time': ['10:00', '11:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A'],
            'qty': [10.0, -5.0],
            'total_eur': [-100.0, 60.0],
            'fee_eur': [-1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-05'), pd.to_datetime('2023-06-15')]
        }
        df_t = pd.DataFrame(trans_data)

        acc_data = {
            'date': ['20-03-2023'],
            'product': ['PRODUCT_A'],
            'isin': ['ISIN_A'],
            'desc': ['Dividendo'],
            'amount_fix': [10.0],
            'currency_fix': ['EUR'],
            'date_obj': [pd.to_datetime('2023-03-20')]
        }
        df_a = pd.DataFrame(acc_data)

        result = process_year(df_t, df_a, 2023)

        # 1. Test Sales Report
        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertEqual(sale['product'], 'PRODUCT_A')
        self.assertEqual(sale['qty'], 5.0)
        self.assertEqual(sale['cost_basis'], 50.0) # 5 shares at 10 each
        self.assertEqual(sale['sale_net'], 60.0)
        self.assertEqual(sale['pnl'], 10.0) # 60 - 50

        # 2. Test Purchases Report
        self.assertEqual(len(result['purchases']), 1)
        purchase = result['purchases'][0]
        self.assertEqual(purchase['product'], 'PRODUCT_A')
        self.assertEqual(purchase['qty'], 10.0)
        self.assertEqual(purchase['total'], 100.0)

        # 3. Test Dividends Report
        self.assertEqual(len(result['dividends']), 1)
        dividend = result['dividends'][0]
        self.assertEqual(dividend['product'], 'PRODUCT_A')
        self.assertEqual(dividend['gross'], 10.0)
        self.assertEqual(dividend['net'], 10.0)

        # 4. Test Final Portfolio
        self.assertEqual(len(result['portfolio']), 1)
        portfolio_item = result['portfolio'][0]
        self.assertEqual(portfolio_item['name'], 'PRODUCT_A')
        self.assertEqual(portfolio_item['qty'], 5.0) # 10 bought - 5 sold
        self.assertAlmostEqual(portfolio_item['total_cost'], 50.0)
        
        # 5. Test Aggregated Stats
        self.assertEqual(result['total_pnl'], 10.0)
        self.assertEqual(result['fees']['trading'], 2.0)

    def test_process_year_sale_at_loss(self):
        """Tests processing a simple sale at a loss."""
        trans_data = {
            'date': ['05-01-2023', '15-06-2023'], 'time': ['10:00', '11:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A'], 'isin': ['ISIN_A', 'ISIN_A'],
            'qty': [10.0, -10.0],
            'total_eur': [-100.0, 80.0], 'fee_eur': [-1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-05'), pd.to_datetime('2023-06-15')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)

        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertEqual(sale['cost_basis'], 100.0)
        self.assertEqual(sale['sale_net'], 80.0)
        self.assertEqual(sale['pnl'], -20.0)
        self.assertEqual(result['total_pnl'], -20.0)

    def test_process_year_wash_sale_rule(self):
        """Tests that the wash sale rule (regla anti-aplicación) is correctly applied."""
        trans_data = {
            'date': ['05-01-2023', '15-03-2023', '10-04-2023'], 'time': ['10:00', '11:00', '12:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A', 'ISIN_A'],
            'qty': [10.0, -10.0, 5.0],
            'total_eur': [-100.0, 80.0, -55.0], 'fee_eur': [-1.0, -1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-05'), pd.to_datetime('2023-03-15'), pd.to_datetime('2023-04-10')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)

        # The sale at a loss on 15-03 is followed by a purchase on 10-04 (within 2 months),
        # so the loss should be blocked.
        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertEqual(sale['pnl'], -20.0)
        self.assertTrue(sale['blocked'])
        
        # The total P&L should not include the blocked loss.
        self.assertEqual(result['total_pnl'], 0.0)

    def test_process_year_fifo_logic(self):
        """Tests that sales correctly use FIFO logic across multiple purchase batches."""
        trans_data = {
            'date': ['05-01-2023', '10-02-2023', '15-06-2023'], 'time': ['10:00', '11:00', '12:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A', 'ISIN_A'],
            'qty': [10.0, 10.0, -15.0],
            'total_eur': [-100.0, -120.0, 250.0], 'fee_eur': [-1.0, -1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-05'), pd.to_datetime('2023-02-10'), pd.to_datetime('2023-06-15')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)

        # Sale of 15 shares should consume all 10 from the first batch (cost 100)
        # and 5 from the second batch (cost 5 * 12 = 60).
        # Total cost basis = 100 + 60 = 160.
        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertAlmostEqual(sale['cost_basis'], 160.0)
        self.assertEqual(sale['pnl'], 250.0 - 160.0)

        # The final portfolio should have 5 shares left from the second batch.
        self.assertEqual(len(result['portfolio']), 1)
        portfolio_item = result['portfolio'][0]
        self.assertEqual(portfolio_item['qty'], 5.0)
        self.assertAlmostEqual(portfolio_item['avg_price'], 12.0) # Avg price of the remaining batch
        self.assertAlmostEqual(portfolio_item['total_cost'], 60.0)

    def test_process_year_sale_with_no_purchase_warning(self):
        """Tests that a warning is generated for a sale with no corresponding purchase."""
        trans_data = {
            'date': ['15-06-2023'], 'time': ['11:00'],
            'product': ['PRODUCT_A'], 'isin': ['ISIN_A'],
            'qty': [-10.0],
            'total_eur': [80.0], 'fee_eur': [-1.0],
            'date_obj': [pd.to_datetime('2023-06-15')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)

        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertTrue(sale['warning'])
        self.assertEqual(sale['cost_basis'], 0)
        self.assertEqual(sale['pnl'], 80.0)

    def test_process_year_special_events(self):
        """Tests processing of special financial events like OPA, CANJE, DERECHOS."""
        trans_data = {
            'date': ['05-01-2023', '15-06-2023', '20-07-2023', '25-08-2023'], 'time': ['10:00', '11:00', '12:00', '13:00'],
            'product': ['PRODUCT_A', 'DERECHOS PRODUCT_A', 'OPA PRODUCT_B - FUSION', 'CANJE PRODUCT_C'],
            'isin': ['ISIN_A', 'ISIN_A', 'ISIN_B', 'ISIN_C'],
            'qty': [10.0, -10.0, -5.0, -20.0],
            'total_eur': [-100.0, 10.0, 50.0, 0.0], 'fee_eur': [-1.0, -0.1, -0.5, -0.2],
            'date_obj': [pd.to_datetime('2023-01-05'), pd.to_datetime('2023-06-15'), pd.to_datetime('2023-07-20'), pd.to_datetime('2023-08-25')]
        }
        df_t = pd.DataFrame(trans_data)

        # Mock df_acc for OPA cash detection
        acc_data_opa = {
            'date': ['20-07-2023'], 'product': ['PRODUCT_B'], 'isin': ['ISIN_B'],
            'desc': ['Efectivo OPA'], 'amount_fix': [50.0], 'currency_fix': ['EUR'],
            'date_obj': [pd.to_datetime('2023-07-20')]
        }
        df_a = pd.DataFrame(acc_data_opa)

        result = process_year(df_t, df_a, 2023)

        self.assertEqual(len(result['sales']), 3) # DERECHOS, OPA, CANJE

        derechos_sale = [s for s in result['sales'] if 'DERECHOS' in s['product']][0]
        self.assertEqual(derechos_sale['product'], 'DERECHOS PRODUCT_A')
        self.assertEqual(derechos_sale['note'], 'DERECHOS')
        self.assertEqual(derechos_sale['pnl'], 10.0) # Sale proceeds - 0 cost basis

        opa_sale = [s for s in result['sales'] if 'OPA' in s['product']][0]
        self.assertEqual(opa_sale['product'], 'OPA PRODUCT_B - FUSION')
        self.assertEqual(opa_sale['note'], 'OPA/FUSIÓN')
        self.assertEqual(opa_sale['pnl'], 50.0) # Sale proceeds - 0 cost basis (no purchase for B)

        canje_sale = [s for s in result['sales'] if 'CANJE' in s['product']][0]
        self.assertEqual(canje_sale['product'], 'CANJE PRODUCT_C')
        self.assertEqual(canje_sale['note'], 'CANJE/SPLIT')
        self.assertEqual(canje_sale['pnl'], 0.0) # Sale proceeds (0.0) - 0 cost basis


    def test_process_year_dividends_wht_and_fees(self):
        """Tests processing of dividends with WHT and connectivity fees."""
        # No transactions, just account entries
        df_t = pd.DataFrame(columns=['date_obj', 'isin', 'qty', 'total_eur', 'fee_eur', 'product'])
        
        acc_data = {
            'date': ['10-06-2023', '10-06-2023', '01-01-2023'],
            'product': ['PRODUCT_C', 'PRODUCT_C', ''],
            'isin': ['ISIN_C', 'ISIN_C', ''],
            'desc': ['Dividendo BRUTO', 'Retención de dividendo', 'Costo de conectividad'],
            'amount_fix': [100.0, -15.0, -2.50],
            'currency_fix': ['EUR', 'EUR', 'EUR'],
            'date_obj': [pd.to_datetime('2023-06-10'), pd.to_datetime('2023-06-10'), pd.to_datetime('2023-01-01')]
        }
        df_a = pd.DataFrame(acc_data)

        result = process_year(df_t, df_a, 2023)

        self.assertEqual(len(result['dividends']), 1)
        dividend = result['dividends'][0]
        self.assertEqual(dividend['gross'], 100.0)
        self.assertEqual(dividend['wht'], 15.0)
        self.assertEqual(dividend['net'], 85.0)

        self.assertEqual(result['fees']['connectivity'], 2.50)

    def test_load_data_frames_alternate_acc_format(self):
        """Tests load_data_frames with an alternate Account.csv format using 'Importe'."""
        trans_csv = (
            '"Fecha","Hora","Producto","ISIN","Número","Total (EUR)","Costes de transacción (EUR)"\n'
            '"25-05-2023","15:30","BUY TESLA","US88160R1014","10.0","-1000.50","-1.00"\n'
        )
        acc_csv_alt = (
            '"Fecha","Producto","ISIN","Importe","Descripción"\n'
            '"10-06-2023","PRODUCT_D","ISIN_D","50.00","Pago de algo"\n'
        )
        
        df_t, df_a = load_data_frames(StringIO(trans_csv), StringIO(acc_csv_alt))
        
        self.assertEqual(len(df_a), 1)
        self.assertEqual(df_a.iloc[0]['product'], "PRODUCT_D")
        self.assertEqual(df_a.iloc[0]['amount_fix'], 50.0)
        self.assertEqual(df_a.iloc[0]['currency_fix'], 'EUR')










if __name__ == '__main__':
    unittest.main()
