import json
import os
import shutil
import tempfile
import unittest

from _load import load

insider = load("trader-pelosi", "insider")

MOCK_PIT_DATA = {
    "data": [
        {
            "symbol": "RELIANCE",
            "secSymbol": "RELIANCE",
            "acqName": "Mukesh Ambani",
            "personCategory": "Promoter",
            "tdpTransactionType": "Buy",
            "secAcq": "50000",
            "valAcq": "125000000",
            "date": "2026-10-15",
            "acqMode": "Market Purchase"
        },
        {
            "symbol": "TCS",
            "acqName": "Tata Sons Private Limited",
            "personCategory": "Promoter Group",
            "tdpTransactionType": "Buy",
            "secAcq": "100000",
            "valAcq": "350000000",
            "date": "2026-10-16",
            "acqMode": "Market Purchase"
        },
        {
            "symbol": "INFY",
            "acqName": "Executive Director",
            "personCategory": "Director",
            "tdpTransactionType": "Sell",
            "secAcq": "10000",
            "valAcq": "15000000",
            "date": "2026-10-14",
            "acqMode": "Market Sale"
        }
    ]
}

MOCK_DEALS_DATA = {
    "data": [
        {
            "symbol": "TATASTEEL",
            "clientName": "LIC OF INDIA",
            "dealType": "BULK",
            "buySell": "BUY",
            "quantityTraded": "5000000",
            "tradePrice": "145.50",
            "tradeDate": "2026-10-18"
        },
        {
            "symbol": "HDFCBANK",
            "clientName": "MORGAN STANLEY ASIA",
            "dealType": "BLOCK",
            "buySell": "SELL",
            "quantityTraded": "1000000",
            "tradePrice": "1650.00",
            "tradeDate": "2026-10-19"
        }
    ]
}


class TestInsider(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.pit_file = os.path.join(self.d, "pit.json")
        with open(self.pit_file, "w", encoding="utf-8") as fh:
            json.dump(MOCK_PIT_DATA, fh)

        self.deals_file = os.path.join(self.d, "deals.json")
        with open(self.deals_file, "w", encoding="utf-8") as fh:
            json.dump(MOCK_DEALS_DATA, fh)

        self.state_file = os.path.join(self.d, "insider_state.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_clean_symbol(self):
        self.assertEqual(insider.clean_symbol("RELIANCE.NS"), "RELIANCE")
        self.assertEqual(insider.clean_symbol("TCS.BO"), "TCS")
        self.assertEqual(insider.clean_symbol("INFY"), "INFY")

    def test_money_inr(self):
        self.assertEqual(insider._money_inr(125000000), "₹12.50 Cr")
        self.assertEqual(insider._money_inr(250000), "₹2.50 L")
        self.assertEqual(insider._money_inr(4500), "₹4,500")

    def test_parse_pit(self):
        rows = insider.parse_pit_data(MOCK_PIT_DATA)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["symbol"], "RELIANCE")
        self.assertEqual(rows[0]["side"], "BUY")
        self.assertEqual(rows[0]["person"], "Mukesh Ambani")
        self.assertEqual(rows[0]["value_formatted"], "₹12.50 Cr")
        self.assertEqual(rows[2]["side"], "SELL")

    def test_filter_pit(self):
        rows = insider.parse_pit_data(MOCK_PIT_DATA)
        
        # Filter by symbol
        rel_only = insider.filter_rows(rows, symbol="RELIANCE.NS")
        self.assertEqual(len(rel_only), 1)
        self.assertEqual(rel_only[0]["symbol"], "RELIANCE")

        # Filter by side
        buys = insider.filter_rows(rows, side="BUY")
        self.assertEqual(len(buys), 2)

        # Filter promoter only
        promoters = insider.filter_rows(rows, promoter_only=True)
        self.assertEqual(len(promoters), 3)

        # Filter min value (>= 5 Crore)
        large = insider.filter_rows(rows, min_val=50000000)
        self.assertEqual(len(large), 2)

    def test_parse_and_filter_deals(self):
        rows = insider.parse_deals_data(MOCK_DEALS_DATA)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "TATASTEEL")
        self.assertEqual(rows[0]["client"], "LIC OF INDIA")
        self.assertEqual(rows[0]["side"], "BUY")
        self.assertEqual(rows[1]["symbol"], "HDFCBANK")
        self.assertEqual(rows[1]["deal_type"], "BLOCK")

    def test_new_tracking_state(self):
        class Args:
            offline = self.pit_file
            state = self.state_file
            symbol = None
            json = True

        a = Args()
        code = insider.cmd_new(a)
        self.assertEqual(code, 0)

        # Second run: nothing new
        code2 = insider.cmd_new(a)
        self.assertEqual(code2, 1)


if __name__ == "__main__":
    unittest.main()
