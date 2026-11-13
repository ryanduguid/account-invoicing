# Copyright 2020 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from unittest import mock

from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tests import Form

from .common import Common

SECTION_GROUPING_FUNCTION = "odoo.addons.account_invoice_section_sale_order.models.account_move.AccountMoveLine._get_section_grouping"  # noqa
SECTION_NAME_FUNCTION = (
    "odoo.addons.base.models.res_users.ResUsers._get_invoice_section_name"
)


class TestInvoiceGroupBySaleOrder(Common):
    def test_grouped_final_invoice_keeps_native_down_payment_section(self):
        pricelist = self.env["product.pricelist"].create(
            {
                "name": "Down payment fixture",
                "currency_id": self.env.company.currency_id.id,
            }
        )
        orders = self.env["sale.order"].browse()
        for product in (self.product_1, self.product_2):
            orders |= self.env["sale.order"].create(
                {
                    "partner_id": self.partner_1.id,
                    "partner_invoice_id": self.partner_1.id,
                    "partner_shipping_id": self.partner_1.id,
                    "pricelist_id": pricelist.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_uom_id": product.uom_id.id,
                                "product_uom_qty": 1,
                                "price_unit": 100,
                                "tax_ids": [Command.clear()],
                            }
                        )
                    ],
                }
            )
        orders.action_confirm()
        self.assertEqual(orders.mapped("amount_total"), [100, 100])
        advance_form = Form(
            self.env["sale.advance.payment.inv"].with_context(
                active_model=orders._name,
                active_id=orders[0].id,
                active_ids=orders[0].ids,
                open_invoices=True,
            )
        )
        advance_form.advance_payment_method = "percentage"
        advance_form.amount = 25
        advance_action = advance_form.save().create_invoices()
        advance = self.env["account.move"].browse(advance_action["res_id"])
        self.assertEqual(advance.amount_total, 25)
        advance.action_post()
        final_form = Form(
            self.env["sale.advance.payment.inv"].with_context(
                active_model=orders._name,
                active_id=orders[0].id,
                active_ids=orders.ids,
                open_invoices=True,
            )
        )
        self.assertEqual(final_form.advance_payment_method, "delivered")
        self.assertTrue(final_form.consolidated_billing)
        final_wizard = final_form.save()
        self.assertTrue(final_wizard.deduct_down_payments)
        final_action = final_wizard.create_invoices()
        invoice = self.env["account.move"].browse(final_action["res_id"])
        self.assertEqual(invoice.amount_untaxed, 175)
        self.assertEqual(invoice.amount_total, 175)
        self.assertEqual(invoice.invoice_line_ids.sale_line_ids.order_id, orders)
        products = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
            and not line.sale_line_ids.filtered("is_downpayment")
        )
        deduction = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
            and line.sale_line_ids.filtered("is_downpayment")
        )
        self.assertEqual(products.product_id, self.product_1 | self.product_2)
        self.assertEqual(sum(products.mapped("price_subtotal")), 200)
        self.assertEqual(len(deduction), 1)
        self.assertEqual(deduction.price_subtotal, -25)
        self.assertEqual(deduction.sale_line_ids.order_id, orders[0])
        sections = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "line_section"
        )
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections.mapped("name").count(orders[0].name), 1)
        self.assertEqual(sections.mapped("name").count(orders[1].name), 1)
        native_section = sections.filtered(
            lambda line: line.name not in orders.mapped("name")
        )
        self.assertEqual(len(native_section), 1)
        self.assertEqual(native_section.name, "Down Payments")
        self.assertFalse(native_section.sale_line_ids)
        invoice.action_post()
        for document, total in ((advance, 25), (invoice, 175)):
            self.assertEqual(document.state, "posted")
            self.assertEqual(sum(document.line_ids.mapped("balance")), 0)
            receivable = document.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            )
            self.assertEqual(sum(receivable.mapped("balance")), total)

    def test_create_invoice(self):
        """Check invoice is generated  with sale order sections."""
        result = {
            10: (
                "".join([self.order1_p1.name, " - ", self.order1_p1.client_order_ref]),
                "line_section",
            ),
            20: (f"{self.product_1.name}\norder 1 line 1", "product"),
            30: (f"{self.product_2.name}\norder 1 line 2", "product"),
            40: (self.order2_p1.name, "line_section"),
            50: (f"{self.product_1.name}\norder 2 line 1", "product"),
            60: (f"{self.product_2.name}\norder 2 line 2", "product"),
        }
        invoice_ids = (self.order1_p1 + self.order2_p1)._create_invoices()
        self.assertEqual(len(invoice_ids), 1)
        lines = invoice_ids[0].invoice_line_ids.sorted("sequence")
        self.assertEqual(
            [(line.sequence, line.name, line.display_type) for line in lines],
            [(sequence, *expected) for sequence, expected in sorted(result.items())],
        )

    def test_create_invoice_with_currency(self):
        """Check invoice is generated with a correct total amount"""
        orders = self.order1_p1 | self.order2_p1
        invoices = orders._create_invoices()
        self.assertEqual(invoices.amount_untaxed, 80)

    def test_create_invoice_with_default_journal(self):
        """Using a specific journal for the invoice should not be broken"""
        journal = self.env["account.journal"].search(
            Domain("type", "=", "sale"), limit=1
        )
        (self.order1_p1 + self.order2_p1).with_context(
            default_journal_id=journal.id
        )._create_invoices()

    def test_create_invoice_no_section(self):
        """Check invoice for only one sale order

        No need to create sections

        """
        invoice_id = (self.order1_p1)._create_invoices()
        line_sections = invoice_id.line_ids.filtered(
            lambda r: r.display_type == "line_section"
        )
        self.assertEqual(len(line_sections), 0)

    def test_custom_name_scheme_literal(self):
        """Check that a quoted literal can be used as section name."""
        self.partner_1.invoice_section_name_scheme = "'Group'"
        invoice = (self.order1_p1 + self.order2_p1)._create_invoices()
        sections = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "line_section"
        ).sorted("sequence")
        self.assertEqual(sections.mapped("name"), ["Group", "Group"])

    def test_unknown_invoice_section_grouping_value(self):
        """Check an error is raised when invoice_section_grouping value is
        unknown
        """
        mock_company_section_grouping = mock.patch.object(
            type(self.env.company),
            "invoice_section_grouping",
            new_callable=mock.PropertyMock,
        )
        with mock_company_section_grouping as mocked_company_section_grouping:
            mocked_company_section_grouping.return_value = "unknown"
            with self.assertRaises(UserError):
                (self.order1_p1 + self.order2_p1)._create_invoices()

    def test_custom_grouping_by_sale_order_user(self):
        """Check custom grouping by sale order user.

        By mocking account.move.line_get_section_grouping and creating
        res.users.get_invoice_section_name, this test ensures custom grouping
        is possible by redefining these functions"""
        admin_user = self.env.ref("base.user_admin")
        orders = self.order1_p1 + self.order2_p1
        orders.write({"user_id": admin_user.id})
        sale_order_3 = self.order1_p1.copy({"user_id": self.user_demo.id})
        sale_order_3.order_line[0].name = "order 3 line 1"
        sale_order_3.order_line[1].name = "order 3 line 2"
        sale_order_3.action_confirm()

        with (
            mock.patch(SECTION_GROUPING_FUNCTION) as mocked_get_section_grouping,
            mock.patch(
                SECTION_NAME_FUNCTION, create=True
            ) as mocked_get_invoice_section_name,
        ):
            mocked_get_section_grouping.return_value = "sale_line_ids.order_id.user_id"
            mocked_get_invoice_section_name.return_value = "Mocked value from ResUsers"
            invoice = (orders + sale_order_3)._create_invoices()
            result = {
                10: ("Mocked value from ResUsers", "line_section"),
                20: (f"{self.product_1.name}\norder 1 line 1", "product"),
                30: (f"{self.product_2.name}\norder 1 line 2", "product"),
                40: (f"{self.product_1.name}\norder 2 line 1", "product"),
                50: (f"{self.product_2.name}\norder 2 line 2", "product"),
                60: ("Mocked value from ResUsers", "line_section"),
                70: (f"{self.product_1.name}\norder 3 line 1", "product"),
                80: (f"{self.product_2.name}\norder 3 line 2", "product"),
            }
            self.assertEqual(len(invoice), 1)
            self.assertEqual(
                [
                    (line.sequence, line.name, line.display_type)
                    for line in invoice.invoice_line_ids.sorted("sequence")
                ],
                [
                    (sequence, *expected)
                    for sequence, expected in sorted(result.items())
                ],
            )
