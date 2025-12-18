import unittest
import os
import pandas as pd
from degiro_app.logic import analyze_full_history

class TestIntegrationRealData(unittest.TestCase):
    def test_full_process_real_data(self):
        # Paths to the real CSV files in the root directory
        trans_path = 'Transactions.csv'
        acc_path = 'Account.csv'
        
        # Verify files exist before running to avoid silly errors
        if not os.path.exists(trans_path) or not os.path.exists(acc_path):
            self.skipTest("Real data files not found in root directory.")
            
        with open(trans_path, 'r', encoding='utf-8') as ft, \
             open(acc_path, 'r', encoding='utf-8') as fa:
             
             # Call the main analysis function
             result = analyze_full_history(ft, fa)
             
        # Basic assertions to ensure the process completed and returned data
        self.assertIsInstance(result, dict)
        self.assertIn('years', result)
        years = result['years']
        self.assertTrue(len(years) > 0, "Should have processed at least one year.")
        
        print("\nProcessed Years:", list(years.keys()))
        
        for year, data in years.items():
            sales = data.get('sales', [])
            blocked_sales = [s for s in sales if s.get('blocked')]
            warnings = [s for s in sales if s.get('warning')]
            
            print(f"Year {year}: Sales={len(sales)}, "
                  f"Divs={len(data.get('dividends', []))}, "
                  f"PnL={data.get('total_pnl', 0.0):.2f}")
            
            if blocked_sales:
                print(f"  [!] {len(blocked_sales)} Blocked Sales (Wash Sale Rule) in {year}")
                for s in blocked_sales:
                     print(f"      - {s['product']} ({s['date']}): Loss {s['pnl']:.2f}")

            if warnings:
                print(f"  [?] {len(warnings)} Warnings in {year}")
                for s in warnings:
                     print(f"      - {s['product']} ({s['date']}): {s.get('note', 'No details')}")

            # Sanity checks
            self.assertIsNotNone(data.get('total_pnl'))
            self.assertIsInstance(data.get('portfolio'), list)

if __name__ == '__main__':
    unittest.main()
