# Copyright 2023 Moduon Team S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from datetime import timedelta

from odoo import Command, fields
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountInvoiceDiscountDate(AccountTestInvoicingCommon):
    def test_later_term_date_preserves_the_earliest_discount_date(self):
        term = self.env["account.payment.term"].create(
            {
                "name": "30% now, 70% in 30 days",
                "early_discount": False,
                "line_ids": [
                    Command.create(
                        {"value": "percent", "nb_days": 0, "value_amount": 30}
                    ),
                    Command.create(
                        {"value": "percent", "nb_days": 30, "value_amount": 70}
                    ),
                ],
            }
        )
        today = fields.Date.today()
        normal_date = today + timedelta(days=5)
        early_date = today + timedelta(days=3)
        later_date = today + timedelta(days=8)
        for move_type in ("out_invoice", "in_invoice"):
            with self.subTest(move_type=move_type):
                invoice = self._create_invoice(
                    move_type=move_type, invoice_payment_term_id=term.id
                )
                term_lines = invoice.line_ids.filtered_domain(
                    [("display_type", "=", "payment_term")]
                ).sorted("date_maturity")
                self.assertEqual(len(term_lines), 2)
                term_lines.discount_date = normal_date
                self.assertEqual(invoice.discount_date, normal_date)
                term_lines[0].discount_date = early_date
                self.assertEqual(invoice.discount_date, early_date)
                term_lines[1].discount_date = later_date
                self.assertEqual(
                    term_lines.mapped("discount_date"), [early_date, later_date]
                )
                self.assertEqual(invoice.discount_date, early_date)
                invoice.flush_recordset(["discount_date"])
                invoice.invalidate_recordset(["discount_date"])
                self.assertEqual(invoice.discount_date, early_date)

    def test_discount_date_propagation(self):
        """Test discount date is computed from the payment term lines"""
        normal_discount_date = fields.Date.today() + timedelta(days=5)
        early_discount_date = fields.Date.today() + timedelta(days=3)
        for move_type in {"out_invoice", "in_invoice"}:
            with self.subTest(move_type=move_type):
                invoice = self._create_invoice(move_type=move_type)
                term_lines = invoice.line_ids.filtered(
                    lambda line: line.display_type == "payment_term"
                )
                term_lines.discount_date = normal_discount_date
                self.assertEqual(invoice.discount_date, normal_discount_date)
                # The earliest line discount date is set on the move
                term_lines[:1].discount_date = early_discount_date
                self.assertEqual(invoice.discount_date, early_discount_date)
