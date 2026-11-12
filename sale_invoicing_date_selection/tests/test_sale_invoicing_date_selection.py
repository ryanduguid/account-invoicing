# Copyright 2022 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields
from odoo.tests import Form

from odoo.addons.base.tests.common import BaseCommon


class TestSaleInvoicingDateSelection(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "partner - test"})
        cls.partner_1 = cls.env["res.partner"].create({"name": "partner1 - test"})
        cls.product = cls.env["product.product"].create(
            {"name": "test invoicing", "type": "service", "invoice_policy": "order"}
        )

    def _create_sale_order(self, partner):
        with Form(self.env["sale.order"]) as sale_form:
            sale_form.partner_id = partner
            with sale_form.order_line.new() as so_line_form:
                so_line_form.product_id = self.product
                so_line_form.price_unit = 100.00
        return sale_form.save()

    def test_regular_invoicing(self):
        order = self._create_sale_order(self.partner)
        order.action_confirm()
        wiz = (
            self.env["sale.advance.payment.inv"]
            .with_context(
                active_model="sale.order",
                active_id=order.id,
                active_ids=order.ids,
                open_invoices=True,
            )
            .create({"invoice_date": "2022-11-01"})
        )
        action = wiz.create_invoices()
        invoices = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(fields.Date.to_string(invoices[0].invoice_date), "2022-11-01")

    def test_advance_invoice(self):
        # check creating invoices when advanced method is not delivered
        order = self._create_sale_order(self.partner_1)
        order.action_confirm()
        wiz = (
            self.env["sale.advance.payment.inv"]
            .with_context(
                active_model="sale.order",
                active_id=order.id,
                active_ids=order.ids,
                open_invoices=True,
            )
            .create({"invoice_date": "2024-03-01"})
        )
        # set values by code as there are invisible fields
        wiz.advance_payment_method = "fixed"
        wiz.fixed_amount = 10
        action = wiz.create_invoices()
        invoices = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(fields.Date.to_string(invoices[0].invoice_date), "2024-03-01")

    def test_down_payment_without_selected_date_uses_the_posting_date(self):
        order = self._create_sale_order(self.partner)
        order.order_line.tax_ids = False
        order.action_confirm()
        wizard = (
            self.env["sale.advance.payment.inv"]
            .with_context(
                active_model="sale.order",
                active_id=order.id,
                active_ids=order.ids,
                open_invoices=True,
            )
            .create(
                {
                    "advance_payment_method": "fixed",
                    "fixed_amount": 10,
                    "invoice_date": False,
                }
            )
        )
        action = wizard.create_invoices()
        invoice = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(invoice, order.invoice_ids)
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.amount_untaxed, 10)
        self.assertEqual(invoice.amount_total, 10)
        self.assertTrue(invoice.invoice_line_ids.sale_line_ids.is_downpayment)
        today = fields.Date.context_today(invoice)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.invoice_date, today)
