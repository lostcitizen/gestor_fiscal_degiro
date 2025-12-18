import unittest
import pandas as pd
from datetime import timedelta
from degiro_app.logic import process_year, analyze_full_history, load_data_frames
from io import StringIO

class TestLogicScenarios(unittest.TestCase):

    def test_wash_sale_purchase_before_sale(self):
        """
        Tests that a purchase BEFORE the sale (within 2 months) triggers the wash sale rule.
        """
        # Loss of 20 EUR. Purchase of same ISIN 1 month before.
        trans_data = {
            'date': ['15-02-2023', '15-03-2023'], 'time': ['10:00', '11:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A'],
            'qty': [10.0, -10.0],
            'total_eur': [-100.0, 80.0], 'fee_eur': [-1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-02-15'), pd.to_datetime('2023-03-15')]
        }
        # But wait, to have a "purchase before sale" that blocks a loss, 
        # usually the wash sale rule (in many jurisdictions) applies if you buy "replacement shares".
        # If I buy 10, then sell those same 10, that's just closing the position.
        # The rule usually implies I still hold shares or bought new ones.
        # If I buy 10 (Feb), Buy 10 (Mar 1), Sell 10 (Mar 15) at loss.
        # The "Buy 10 (Mar 1)" is within 2 months before the sale.
        # Let's try that scenario.
        
        trans_data_2 = {
            'date': ['15-01-2023', '01-03-2023', '15-03-2023'], 
            'time': ['10:00', '11:00', '12:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A', 'ISIN_A'],
            'qty': [10.0, 10.0, -10.0], # Buy 10, Buy 10, Sell 10
            'total_eur': [-100.0, -100.0, 80.0], # Cost 10 each. Sell at 8. Loss 20.
            'fee_eur': [-1.0, -1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-15'), pd.to_datetime('2023-03-01'), pd.to_datetime('2023-03-15')]
        }
        
        df_t = pd.DataFrame(trans_data_2)
        result = process_year(df_t, pd.DataFrame(), 2023)
        
        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertEqual(sale['pnl'], -20.0)
        self.assertTrue(sale['blocked'], "Loss should be blocked due to purchase 14 days before sale")

    def test_wash_sale_purchase_outside_window(self):
        """
        Tests that a purchase OUTSIDE the 2-month window does NOT trigger the rule.
        """
        trans_data = {
            'date': ['15-01-2023', '15-03-2023', '20-06-2023'], # Purchase > 2 months after sale
            'time': ['10:00', '11:00', '12:00'],
            'product': ['PRODUCT_A', 'PRODUCT_A', 'PRODUCT_A'],
            'isin': ['ISIN_A', 'ISIN_A', 'ISIN_A'],
            'qty': [10.0, -10.0, 10.0],
            'total_eur': [-100.0, 80.0, -100.0],
            'fee_eur': [-1.0, -1.0, -1.0],
            'date_obj': [pd.to_datetime('2023-01-15'), pd.to_datetime('2023-03-15'), pd.to_datetime('2023-06-20')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)
        
        self.assertEqual(len(result['sales']), 1)
        sale = result['sales'][0]
        self.assertEqual(sale['pnl'], -20.0)
        self.assertFalse(sale['blocked'], "Loss should NOT be blocked, purchase is > 62 days later")

    def test_fifo_interleaved_transactions(self):
        """
        Tests FIFO logic with interleaved buys and sells.
        1. Buy 10 @ 10 (Batch A)
        2. Sell 5 (from Batch A) -> Remaining A: 5
        3. Buy 10 @ 20 (Batch B)
        4. Sell 10 (5 from Batch A, 5 from Batch B)
        """
        trans_data = {
            'date': ['01-01-2023', '01-02-2023', '01-03-2023', '01-04-2023'],
            'time': ['10:00', '10:00', '10:00', '10:00'],
            'product': ['P', 'P', 'P', 'P'],
            'isin': ['I', 'I', 'I', 'I'],
            'qty': [10.0, -5.0, 10.0, -10.0],
            'total_eur': [-100.0, 60.0, -200.0, 150.0], # Sell 1 @ 12/share, Sell 2 @ 15/share
            'fee_eur': [0, 0, 0, 0],
            'date_obj': [pd.to_datetime('2023-01-01'), pd.to_datetime('2023-02-01'), 
                         pd.to_datetime('2023-03-01'), pd.to_datetime('2023-04-01')]
        }
        df_t = pd.DataFrame(trans_data)
        result = process_year(df_t, pd.DataFrame(), 2023)
        
        self.assertEqual(len(result['sales']), 2)
        
        # First sale: 5 shares. Cost basis: 5 * 10 = 50. Proceeds: 60. PnL: 10.
        s1 = result['sales'][0]
        self.assertEqual(s1['qty'], 5.0)
        self.assertEqual(s1['cost_basis'], 50.0)
        self.assertEqual(s1['pnl'], 10.0)
        
        # Second sale: 10 shares.
        # Should take remaining 5 from Batch A (@10) and 5 from Batch B (@20).
        # Cost basis: (5 * 10) + (5 * 20) = 50 + 100 = 150.
        # Proceeds: 150. PnL: 0.
        s2 = result['sales'][1]
        self.assertEqual(s2['qty'], 10.0)
        self.assertEqual(s2['cost_basis'], 150.0)
        self.assertEqual(s2['pnl'], 0.0)
        
        # Remaining portfolio: 5 shares from Batch B (@20). Total cost 100.
        self.assertEqual(len(result['portfolio']), 1)
        p = result['portfolio'][0]
        self.assertEqual(p['qty'], 5.0)
        self.assertEqual(p['total_cost'], 100.0)

    def test_multi_year_carryover(self):
        """
        Tests that portfolio state is correctly carried over years using analyze_full_history.
        """
        # Year 1 (2022): Buy 10 @ 100.
        # Year 2 (2023): Sell 5.
        
        trans_csv = (
            '"Fecha","Hora","Producto","ISIN","Número","Total (EUR)","Costes"\n'
            '"01-01-2022","10:00","PROD","ISIN1","10","-1000","0"\n'
            '"01-01-2023","10:00","PROD","ISIN1","-5","600","0"\n'
        )
        
        trans_stream = StringIO(trans_csv)
        acc_stream = StringIO("") # Empty account file
        
        data = analyze_full_history(trans_stream, acc_stream)
        
        years = data['years']
        self.assertIn(2022, years)
        self.assertIn(2023, years)
        
        # Check 2022
        y22 = years[2022]
        self.assertEqual(len(y22['purchases']), 1)
        self.assertEqual(len(y22['sales']), 0)
        self.assertEqual(len(y22['portfolio']), 1)
        self.assertEqual(y22['portfolio'][0]['qty'], 10.0)
        
        # Check 2023
        y23 = years[2023]
        self.assertEqual(len(y23['sales']), 1)
        sale = y23['sales'][0]
        self.assertEqual(sale['qty'], 5.0)
        # Cost basis should be derived from 2022 purchase: 5 * (1000/10) = 500
        self.assertEqual(sale['cost_basis'], 500.0)
        self.assertEqual(sale['pnl'], 100.0) # 600 - 500
        
        # Remaining portfolio in 2023
        self.assertEqual(len(y23['portfolio']), 1)
        self.assertEqual(y23['portfolio'][0]['qty'], 5.0)
        self.assertEqual(y23['portfolio'][0]['total_cost'], 500.0)

    def test_quiet_year_with_portfolio(self):
        """
        Tests a year with no transactions but with a holding portfolio.
        """
        trans_csv = (
            '"Fecha","Hora","Producto","ISIN","Número","Total (EUR)","Costes"\n'
            '"01-01-2022","10:00","PROD","ISIN1","10","-1000","0"\n'
            # No transactions in 2023
            '"01-01-2024","10:00","PROD","ISIN1","-10","1200","0"\n'
        )
        trans_stream = StringIO(trans_csv)
        acc_stream = StringIO("") 
        
        data = analyze_full_history(trans_stream, acc_stream)
        
        self.assertIn(2023, data['years'])
        y23 = data['years'][2023]
        self.assertEqual(len(y23['sales']), 0)
        self.assertEqual(len(y23['purchases']), 0)
        self.assertEqual(len(y23['portfolio']), 1)
        self.assertEqual(y23['portfolio'][0]['qty'], 10.0)

if __name__ == '__main__':
    unittest.main()
