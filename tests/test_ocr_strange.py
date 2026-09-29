import unittest

from ocr_strange import clean_text, repair_text


class OcrStrangeTest(unittest.TestCase):
    def test_clean_text_normalizes_spacing_and_quotes(self):
        self.assertEqual(clean_text("  Hello   world\r\n\r\n\r\n\u201cOCR\u201d "), 'Hello world\n\n"OCR"')

    def test_repair_text_extracts_and_normalizes_invoice_fields(self):
        result = repair_text(
            """
            INVOICE N0: INV-I042
            Date: 3O/O9/2O26
            TotaI: $I,29O.OO
            Email: billing@example.corn
            """,
            schema={
                "invoice_number": "string",
                "date": "date",
                "total": "money",
                "email": "email",
            },
        )

        self.assertEqual(result.data["invoice_number"], "INV-1042")
        self.assertEqual(result.data["date"], "2026-09-30")
        self.assertEqual(result.data["total"], "1290.00")
        self.assertEqual(result.data["email"], "billing@example.com")
        self.assertGreater(result.confidence["total"], 0.8)
        self.assertTrue(result.review_reasons)

    def test_missing_field_gets_review_reason(self):
        result = repair_text("Total: $10.00", schema={"date": "date"})

        self.assertIsNone(result.data["date"])
        self.assertEqual(result.confidence["date"], 0.0)
        self.assertEqual(result.review_reasons, ["date was not found"])

    def test_repairs_very_noisy_invoice_labels(self):
        result = repair_text(
            """
            lNV0lCE N0: lNV-I042
            lssue Date  :  3O/O9/2O26
            SubtotaI: $ I,OOO.OO
            Tax: $ 29O.OO
            TotaI Due: $ I,29O.OO
            Emaii: biIIing@example.corn
            """,
            schema={
                "invoice_number": "string",
                "date": "date",
                "total": "money",
                "email": "email",
            },
        )

        self.assertEqual(result.data["invoice_number"], "INV-1042")
        self.assertEqual(result.data["date"], "2026-09-30")
        self.assertEqual(result.data["total"], "1290.00")
        self.assertEqual(result.data["email"], "biIIing@example.com")

    def test_does_not_turn_currency_words_into_amounts(self):
        result = repair_text(
            """
            Applicant Name
            John D0e
            Email - john.d0e@exampIe.corn
            Mobile: +I (2O2) 555-OI99
            Amount Due .......... USD I2O.OO
            """,
            schema={"email": "email", "phone": "phone", "total": "money"},
        )

        self.assertEqual(result.data["email"], "john.d0e@example.com")
        self.assertEqual(result.data["phone"], "12025550199")
        self.assertEqual(result.data["total"], "120.00")


if __name__ == "__main__":
    unittest.main()
