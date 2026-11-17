import unittest
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app import chat as C

class TestChatIntents(unittest.TestCase):
    def test_format_inr(self):
        self.assertEqual(C.format_inr(0), "₹0")
        self.assertEqual(C.format_inr(500), "₹500")
        self.assertEqual(C.format_inr(1500), "₹1,500")
        self.assertEqual(C.format_inr(25000), "₹25,000")
        self.assertEqual(C.format_inr(125000), "₹1,25,000")
        self.assertEqual(C.format_inr(314926.28), "₹3,14,926")
        self.assertEqual(C.format_inr(-50000), "-₹50,000")

    def test_chat_queries(self):
        queries = [
            "should I order Nebulizer?",
            "should I buy Paracetamol?",
            "do we need more Cefixime?",
            "what should I order from Apex?",
            "What items need reordering?",
            "What items are overstocked?",
            "How is my profit and margin?",
            "What are my expenses?",
            "What should I do today?",
            "Any stock alerts or expiring batches?",
            "What are my best selling products?",
            "What is the 30-day sales forecast?",
            "Why was 18 Mar a spike?",
            "Are any business days unclosed?",
            "Are there any profit leaks or discount losses?",
            "Which chronic patients are due for refill?",
            "Which products sell together?",
            "Compare brands in Paracetamol",
            "Who are my top customers?",
            "hello",
        ]
        for q in queries:
            resp = C.handle_chat_message(q)
            self.assertIn("reply", resp)
            self.assertTrue(len(resp["reply"]) > 20, f"Reply too short for query: {q}")
            self.assertNotIn("₹314,926", resp["reply"], "Found raw non-INR formatted currency")
            print(f"Query: '{q}'\nReply:\n{resp['reply'][:120]}...\n{'-'*40}")

if __name__ == "__main__":
    unittest.main()
