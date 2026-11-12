from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestReceipts(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_receipt_journal = cls.env["account.journal"].create(
            {
                "name": "Sale Receipts Journal",
                "code": "SREC",
                "type": "sale",
                "receipts": True,
                "sequence": 99,
            }
        )
        cls.in_receipt_journal = cls.env["account.journal"].create(
            {
                "name": "Purchase Receipts Journal",
                "code": "PREC",
                "type": "purchase",
                "receipts": True,
                "sequence": 99,
            }
        )

    def test_receipt_journal_sequence(self):
        with self.assertRaises(ValidationError):
            self.out_receipt_journal.write({"sequence": 1})
        with self.assertRaises(ValidationError):
            self.in_receipt_journal.write({"sequence": 1})

    def test_company_can_configure_a_receipt_journal_first(self):
        company = self.env["res.company"].create({"name": "Receipt journal startup"})
        self.env.user.company_ids |= company
        journals = self.env["account.journal"].with_company(company)
        for journal_type, move_type, code in (
            ("sale", "out_receipt", "FRS"),
            ("purchase", "in_receipt", "FRP"),
        ):
            with self.subTest(journal_type=journal_type):
                self.assertFalse(
                    journals.search_count(
                        [
                            ("company_id", "=", company.id),
                            ("type", "=", journal_type),
                        ]
                    )
                )
                journal = journals.create(
                    {
                        "name": "First receipt journal " + code,
                        "code": code,
                        "type": journal_type,
                        "company_id": company.id,
                        "receipts": True,
                        "sequence": 1,
                    }
                )
                self.assertEqual(journal.company_id, company)
                self.assertTrue(journal.receipts)
                self.assertEqual(journal.sequence, 1)
                self.assertEqual(
                    journal.action_create_new()["context"]["default_move_type"],
                    move_type,
                )
                action = journal.open_action()
                self.assertEqual(action["context"]["default_move_type"], move_type)
                self.assertEqual(action["domain"], [("move_type", "=", move_type)])

    def test_receipt_default_journal(self):
        """Test default values for receipt."""
        for move_type in {"out_receipt", "in_receipt"}:
            with self.subTest(move_type=move_type):
                receipt = self.init_invoice(
                    move_type, products=self.product_a + self.product_b
                )
                self.assertTrue(receipt.journal_id.receipts)

    def test_receipt_exclusive_journal(self):
        """Test exclusivity constraint for receipt journals."""
        for move_type in {"out_receipt", "in_receipt"}:
            with self.subTest(move_type=move_type):
                receipt = self.init_invoice(
                    move_type, products=self.product_a + self.product_b
                )
                non_receipt_journals = self.env["account.journal"].search(
                    [
                        ("type", "=", receipt.journal_id.type),
                        ("company_id", "=", receipt.journal_id.company_id.id),
                        ("receipts", "=", False),
                    ]
                )
                with self.assertRaises(ValidationError):
                    receipt.write({"journal_id": non_receipt_journals.ids[0]})

    def test_action_open_dashboard(self):
        """Test action_create_new and open_action"""
        action = self.out_receipt_journal.action_create_new()
        self.assertEqual(action["context"]["default_move_type"], "out_receipt")
        action = self.in_receipt_journal.action_create_new()
        self.assertEqual(action["context"]["default_move_type"], "in_receipt")
        action = self.out_receipt_journal.open_action()
        self.assertEqual(action["context"]["default_move_type"], "out_receipt")
        self.assertEqual(action["domain"], [("move_type", "=", "out_receipt")])
        action = self.in_receipt_journal.open_action()
        self.assertEqual(action["context"]["default_move_type"], "in_receipt")
        self.assertEqual(action["domain"], [("move_type", "=", "in_receipt")])

    def test_ordinary_journal_dashboard_keeps_invoice_defaults(self):
        for journal_type, move_type in (
            ("sale", "out_invoice"),
            ("purchase", "in_invoice"),
        ):
            with self.subTest(journal_type=journal_type):
                journal = self.env["account.journal"].search(
                    [
                        ("type", "=", journal_type),
                        ("company_id", "=", self.env.company.id),
                        ("receipts", "=", False),
                    ],
                    limit=1,
                )
                self.assertTrue(journal)
                for action in (journal.action_create_new(), journal.open_action()):
                    self.assertEqual(action["context"]["default_move_type"], move_type)

    def test_ordinary_invoices_cannot_use_receipt_only_journals(self):
        for move_type, receipt_journal in (
            ("out_invoice", self.out_receipt_journal),
            ("in_invoice", self.in_receipt_journal),
        ):
            with self.subTest(move_type=move_type):
                invoice = self.init_invoice(
                    move_type, products=self.product_a + self.product_b
                )
                journal = invoice.journal_id
                self.assertFalse(journal.receipts)
                with (
                    self.assertRaisesRegex(
                        ValidationError, "Receipt Journal is restricted to Receipts"
                    ),
                    self.env.cr.savepoint(),
                ):
                    invoice.write({"journal_id": receipt_journal.id})
                self.assertEqual(invoice.journal_id, journal)

    def test_explicit_ordinary_journal_redirects_receipts_to_matching_currency(self):
        currency = self.env.ref("base.EUR")
        if currency == self.env.company.currency_id:
            currency = self.env.ref("base.USD")
        currency.active = True
        for move_type, journal_type, code in (
            ("out_receipt", "sale", "SFCR"),
            ("in_receipt", "purchase", "PFCR"),
        ):
            with self.subTest(move_type=move_type):
                ordinary = self.env["account.journal"].search(
                    [
                        ("type", "=", journal_type),
                        ("receipts", "=", False),
                        ("company_id", "=", self.env.company.id),
                    ],
                    limit=1,
                )
                self.assertTrue(ordinary)
                matching = self.env["account.journal"].create(
                    {
                        "name": "Fabricated currency receipt journal " + code,
                        "code": code,
                        "type": journal_type,
                        "receipts": True,
                        "sequence": 99,
                        "currency_id": currency.id,
                        "company_id": ordinary.company_id.id,
                    }
                )
                receipt = (
                    self.env["account.move"]
                    .with_context(
                        default_move_type=move_type,
                        default_currency_id=currency.id,
                    )
                    .create(
                        {
                            "move_type": move_type,
                            "journal_id": ordinary.id,
                            "currency_id": currency.id,
                        }
                    )
                )
                self.assertEqual(receipt.journal_id, matching)
                self.assertEqual(receipt.currency_id, currency)
                self.assertEqual(receipt.move_type, move_type)
