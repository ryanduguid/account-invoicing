# Copyright 2017 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountInvoiceMerge(AccountTestInvoicingCommon):
    """
    Tests for Account Invoice Merge.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "sale.order" in cls.env.registry:
            cls.env.user.write(
                {"group_ids": [(4, cls.env.ref("sales_team.group_sale_manager").id)]}
            )
        cls.company = cls.company_data["company"]
        cls.company_data2 = cls.setup_other_company()
        cls.company2 = cls.company_data2["company"]
        companies = cls.company | cls.company2
        cls.env.user.write(
            {
                "company_ids": [Command.set(companies.ids)],
            }
        )
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,
                allowed_company_ids=companies.ids,
            )
        )
        invoice_date = fields.Date.today()
        cls.invoice1 = cls.init_invoice(
            move_type="out_invoice",
            partner=cls.partner_a,
            invoice_date=invoice_date,
            products=cls.product_a,
        )
        cls.now = cls.invoice1.create_date
        cls.invoice2 = cls.init_invoice(
            move_type="out_invoice",
            partner=cls.partner_a,
            invoice_date=invoice_date,
            products=cls.product_a,
        )
        cls.invoice3 = cls.init_invoice(
            move_type="out_invoice",
            partner=cls.partner_b,
            invoice_date=invoice_date,
            products=cls.product_a,
        )
        cls.invoice4 = cls.init_invoice(
            move_type="in_invoice",
            partner=cls.partner_a,
            invoice_date=invoice_date,
            products=cls.product_a,
        )
        cls.invoice5 = cls.init_invoice(
            move_type="out_invoice",
            partner=cls.partner_a,
            invoice_date=invoice_date,
            products=cls.product_a,
        )
        cls.invoice6 = cls.init_invoice(
            move_type="out_invoice",
            partner=cls.partner_a,
            products=cls.product_a,
            invoice_date=invoice_date,
            company=cls.company2,
        )

        cls.inv_model = cls.env["account.move"]
        cls.wiz = cls.env["invoice.merge"]

    def _get_wizard(self, active_ids):
        return self.wiz.with_context(
            active_ids=active_ids,
            active_model="account.move",
        ).create({})

    def test_invoice_merge(self):
        self.assertEqual(len(self.invoice1.invoice_line_ids), 1)
        self.assertEqual(len(self.invoice2.invoice_line_ids), 1)
        invoice_len_args = [
            ("create_date", ">=", self.now),
            ("partner_id", "=", self.partner_a.id),
            ("state", "=", "draft"),
        ]
        start_inv = self.inv_model.search(invoice_len_args)
        self.assertEqual(len(start_inv), 5)

        wiz = self._get_wizard([self.invoice1.id, self.invoice2.id])
        action = wiz.merge_invoices()

        self.assertLessEqual(
            {
                "type": "ir.actions.act_window",
                "binding_view_types": "list,form",
                "xml_id": "account.action_move_out_invoice_type",
            }.items(),
            action.items(),
            "There was an error and the two invoices were not merged.",
        )

        end_inv = self.inv_model.search(invoice_len_args)
        single_end_inv = end_inv[-1]
        self.assertEqual(len(end_inv), 4)
        self.assertEqual(len(single_end_inv.invoice_line_ids), 1)
        self.assertEqual(single_end_inv.invoice_line_ids.quantity, 2.0)

    def test_invoice_merge_keep_references(self):
        self.invoice1.write({"name": "INV-REF-1"})
        self.invoice2.write({"name": "INV-REF-2"})
        invoices_info = (self.invoice1 | self.invoice2).do_merge(keep_references=True)
        merged_invoice = self.inv_model.browse(next(iter(invoices_info)))
        self.assertEqual(
            merged_invoice.name,
            "INV-REF-1 INV-REF-2",
        )

    def test_invoice_merge_preserves_distinct_payment_references_once(self):
        invoices = self.invoice1 | self.invoice2 | self.invoice5
        for invoice, reference in zip(
            invoices, ("REF-A", "REF-B", "REF-B"), strict=True
        ):
            invoice.payment_reference = reference
            invoice.invoice_line_ids.write(
                {"price_unit": 100.0, "quantity": 1, "tax_ids": [Command.clear()]}
            )
        invoices_info = invoices.do_merge(keep_references=True)
        self.assertEqual(len(invoices_info), 1)
        merged = self.inv_model.browse(next(iter(invoices_info)))
        self.assertEqual(merged.payment_reference, "REF-A REF-B")
        self.assertEqual(len(merged.invoice_line_ids), 1)
        self.assertEqual(merged.invoice_line_ids.quantity, 3)
        self.assertEqual(merged.amount_untaxed, 300.0)
        self.assertEqual(merged.amount_total, 300.0)

    def test_invoice_merge_preserves_and_groups_analytic_allocations(self):
        plan = self.env["account.analytic.plan"].create(
            {"name": "Merge allocation plan"}
        )
        accounts = self.env["account.analytic.account"].create(
            [
                {"name": name, "plan_id": plan.id, "company_id": self.company.id}
                for name in ("Preparation", "Review")
            ]
        )
        first, second = (str(account.id) for account in accounts)
        matching = {first: 60, second: 40}
        matching_reordered = {second: 40, first: 60}
        different = {first: 20, second: 80}
        invoices = self.invoice1 | self.invoice2 | self.invoice5
        for invoice, distribution in zip(
            invoices, (matching, matching_reordered, different), strict=True
        ):
            invoice.invoice_line_ids.write(
                {
                    "price_unit": 100,
                    "quantity": 1,
                    "tax_ids": [Command.clear()],
                    "analytic_distribution": distribution,
                }
            )
        line_model = self.env["account.move.line"]
        first_line = line_model.new({"analytic_distribution": matching})
        second_line = line_model.new({"analytic_distribution": matching_reordered})
        self.assertEqual(list(first_line.analytic_distribution), [first, second])
        self.assertEqual(list(second_line.analytic_distribution), [second, first])
        self.assertEqual(
            invoices.make_key(first_line, ["analytic_distribution"]),
            invoices.make_key(second_line, ["analytic_distribution"]),
        )
        invoices.invoice_line_ids.flush_recordset(["analytic_distribution"])
        invoices.invoice_line_ids.invalidate_recordset(["analytic_distribution"])
        action = self._get_wizard(invoices.ids).merge_invoices()
        merged = self.inv_model.search(action["domain"]).filtered(
            lambda invoice: invoice.state == "draft"
        )
        self.assertEqual(len(merged), 1)
        self.assertNotIn(merged, invoices)
        self.assertTrue(all(invoice.state == "cancel" for invoice in invoices))
        self.assertAlmostEqual(merged.amount_untaxed, 300)
        self.assertAlmostEqual(merged.amount_tax, 0)
        self.assertAlmostEqual(merged.amount_total, 300)
        lines = merged.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(len(lines), 2)
        for persisted in (False, True):
            if persisted:
                lines.flush_recordset(["analytic_distribution"])
                lines.invalidate_recordset(["analytic_distribution"])
            for distribution, quantity, subtotal in (
                (matching, 2, 200),
                (different, 1, 100),
            ):
                allocated = lines.filtered(
                    lambda line, distribution=distribution: line.analytic_distribution
                    == distribution
                )
                self.assertEqual(len(allocated), 1)
                self.assertAlmostEqual(allocated.quantity, quantity)
                self.assertAlmostEqual(allocated.price_subtotal, subtotal)

    def test_invoice_merge_respects_optional_sum_fields(self):
        drafts = self.invoice1 | self.invoice2
        expected_name = self.invoice1.invoice_line_ids.name
        with patch.object(
            type(drafts),
            "_get_sum_fields",
            return_value=["quantity", "name", "fabricated_optional_amount"],
        ):
            merged = drafts.do_merge()

        invoice = drafts.browse(list(merged))
        self.assertEqual(len(invoice), 1)
        line = invoice.invoice_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.name, expected_name)

    def test_invoice_merge_single_invoice(self):
        invoices_info = self.invoice1.do_merge()
        self.assertFalse(invoices_info)
        self.assertEqual(self.invoice1.state, "draft")

    def test_invoice_merge_keep_empty_lines(self):
        self.invoice1.invoice_line_ids.quantity = 1.0
        self.invoice2.invoice_line_ids.quantity = -1.0
        invoices_info = (self.invoice1 | self.invoice2).do_merge(
            remove_empty_invoice_lines=False
        )
        merged_invoice = self.inv_model.browse(next(iter(invoices_info)))
        self.assertEqual(len(merged_invoice.invoice_line_ids), 1)
        self.assertEqual(merged_invoice.invoice_line_ids.quantity, 0.0)

    def test_merge_wizard_defaults_without_active_invoices(self):
        invoices = self.invoice1 | self.invoice2
        fields_to_preserve = ["state", "name", "amount_total", "invoice_line_ids"]
        before = invoices.read(fields_to_preserve)
        wizard = self.wiz.with_context(
            active_model=False, active_ids=[], active_id=False
        )
        limited = wizard.default_get(["keep_references"])
        self.assertTrue(limited["keep_references"])
        self.assertNotIn("error_message", limited)
        with_error = wizard.default_get(["keep_references", "error_message"])
        self.assertTrue(with_error["keep_references"])
        self.assertFalse(with_error["error_message"])
        invoices.invalidate_recordset(fields_to_preserve)
        self.assertEqual(invoices.read(fields_to_preserve), before)

    def test_error_check(self):
        """Check"""
        # Different partner
        wiz = self._get_wizard([self.invoice1.id, self.invoice3.id])
        self.assertEqual(
            wiz.error_message, "All invoices must have the same: \n- Partner"
        )

        # Check with only one invoice
        wiz = self._get_wizard([self.invoice1.id])
        self.assertEqual(
            wiz.error_message,
            "Please select multiple invoices to merge in the list view.",
        )

        # Check with two different invoice type
        wiz = self._get_wizard([self.invoice1.id, self.invoice4.id])
        self.assertEqual(
            wiz.error_message, "All invoices must have the same: \n- Type\n- Journal"
        )

        # Check with a canceled invoice
        self.invoice5.button_cancel()
        wiz = self._get_wizard([self.invoice1.id, self.invoice5.id])
        self.assertEqual(
            wiz.error_message,
            "All invoices must have the same: \n- Merge-able State (ex : Draft)",
        )

        # Check with another company
        wiz = self._get_wizard([self.invoice1.id, self.invoice6.id])
        self.assertEqual(
            wiz.error_message, "All invoices must have the same: \n- Journal\n- Company"
        )

    def test_callback_different_sale_order_00(self):
        if "sale.order" not in self.env.registry:
            return True
        product_1, product_2 = self.env["product.product"].create(
            [
                {
                    "name": "product 1",
                    "list_price": 5.0,
                },
                {
                    "name": "product 2",
                    "list_price": 10.0,
                },
            ]
        )
        # Test pre-computes of lines with order
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Dummy section",
                        }
                    ),
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Dummy section",
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product_1.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product_2.id,
                        }
                    ),
                ],
            }
        )
        sale_order_2 = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Dummy section",
                        }
                    ),
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Dummy section",
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product_1.id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product_2.id,
                        }
                    ),
                ],
            }
        )
        sale_order.action_confirm()
        sale_order._create_invoices(final=True)
        sale_order_2.action_confirm()
        sale_order_2._create_invoices(final=True)
        invoices = (sale_order | sale_order_2).mapped(
            "order_line.invoice_lines.move_id"
        )
        invoices_info = invoices.do_merge(
            keep_references=False, date_invoice=fields.Date.today()
        )
        invoices_2 = (sale_order | sale_order_2).mapped(
            "order_line.invoice_lines.move_id"
        )
        invoices_2 = invoices_2.filtered(lambda i: i.state == "draft")
        self.assertEqual(sorted(invoices_2.ids), sorted(list(invoices_info.keys())))

    def _add_qty_delivered_and_create_invoice(self, sale_order):
        for line in sale_order.order_line:
            if line.qty_delivered < line.product_uom_qty:
                line.qty_delivered += 1
        sale_order._create_invoices(final=True)

    def _add_qty_received_and_create_invoice(self, purchase_order):
        for line in purchase_order.order_line:
            if line.qty_received < line.product_qty:
                line.qty_received += 1
        purchase_order.action_create_invoice()

    def test_callback_different_sale_order_01(self):
        if "sale.order" not in self.env.registry:
            return True
        product_1, product_2 = self.env["product.product"].create(
            [
                {"name": "product 1", "list_price": 5.0, "invoice_policy": "delivery"},
                {"name": "product 2", "list_price": 10.0, "invoice_policy": "delivery"},
            ]
        )
        # Test pre-computes of lines with order
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create({"product_id": product_1.id, "product_uom_qty": 5}),
                    Command.create({"product_id": product_2.id, "product_uom_qty": 2}),
                ],
            }
        )
        sale_order_2 = sale_order.copy()

        sale_order.action_confirm()
        sale_order_2.action_confirm()

        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order_2)
        self._add_qty_delivered_and_create_invoice(sale_order_2)
        self._add_qty_delivered_and_create_invoice(sale_order_2)

        inv_sale_order = sale_order.mapped("order_line.invoice_lines.move_id")
        inv_sale_order_2 = sale_order_2.mapped("order_line.invoice_lines.move_id")
        total_inv_sale_order = inv_sale_order | inv_sale_order_2

        self.assertEqual(len(inv_sale_order), 3)
        self.assertEqual(len(inv_sale_order_2), 3)
        self.assertEqual(len(total_inv_sale_order), 6)
        for line in (sale_order | sale_order_2).order_line:
            self.assertEqual(line.qty_delivered, min(line.product_uom_qty, 3))
            self.assertEqual(line.qty_invoiced, line.qty_delivered)

        invoices = (
            sale_order.mapped("order_line.invoice_lines.move_id")[:1]
            | sale_order_2.mapped("order_line.invoice_lines.move_id")[:1]
        )
        invoices.do_merge(keep_references=False, date_invoice=fields.Date.today())

        inv_sale_order = sale_order.mapped("order_line.invoice_lines.move_id")
        inv_sale_order_2 = sale_order_2.mapped("order_line.invoice_lines.move_id")
        total_inv_sale_order = inv_sale_order | inv_sale_order_2

        self.assertEqual(len(inv_sale_order), 3)
        self.assertEqual(len(inv_sale_order_2), 3)
        self.assertEqual(len(total_inv_sale_order), 5)
        for line in (sale_order | sale_order_2).order_line:
            self.assertEqual(line.qty_delivered, min(line.product_uom_qty, 3))
            self.assertEqual(line.qty_invoiced, line.qty_delivered)

    def test_callback_updates_each_group_of_merged_sale_invoices(self):
        if "sale.order" not in self.env.registry:
            return True
        products = self.env["product.product"].create(
            [
                {"name": name, "list_price": 5.0, "invoice_policy": "delivery"}
                for name in ("Delivered item", "Offset item")
            ]
        )
        orders = self.env["sale.order"].create(
            [
                {
                    "partner_id": partner.id,
                    "order_line": [
                        Command.create({"product_id": product.id, "product_uom_qty": 2})
                        for product in products
                    ],
                }
                for partner in (self.partner_a, self.partner_b)
            ]
        )
        for order in orders:
            order.action_confirm()
            self._add_qty_delivered_and_create_invoice(order)
            self._add_qty_delivered_and_create_invoice(order)
        original_invoices = orders.order_line.invoice_lines.move_id
        self.assertEqual(len(original_invoices), 4)
        offset_line = orders[0].order_line.filtered_domain(
            [("product_id", "=", products[1].id)]
        )
        offset_line.invoice_lines.sorted("id")[-1].quantity = -1

        merged = original_invoices.do_merge(keep_references=False)

        self.assertEqual(len(merged), 2)
        self.assertEqual(set(original_invoices.mapped("state")), {"cancel"})
        self.assertFalse(offset_line.invoice_lines)
        self.assertEqual(offset_line.qty_invoiced, 0)
        for order in orders:
            invoice = order.order_line.invoice_lines.move_id
            self.assertEqual(len(invoice), 1)
            self.assertIn(invoice.id, merged)
            self.assertEqual(invoice.partner_id, order.partner_id)
            for line in order.order_line - offset_line:
                self.assertEqual(line.qty_invoiced, 2)

    def test_callback_same_sale_order(self):
        if "sale.order" not in self.env.registry:
            return True
        product_1, product_2 = self.env["product.product"].create(
            [
                {"name": "product 1", "list_price": 5.0, "invoice_policy": "delivery"},
                {"name": "product 2", "list_price": 10.0, "invoice_policy": "delivery"},
            ]
        )
        # Test pre-computes of lines with order
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create({"product_id": product_1.id, "product_uom_qty": 5}),
                    Command.create({"product_id": product_2.id, "product_uom_qty": 5}),
                ],
            }
        )

        sale_order.action_confirm()
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)
        self._add_qty_delivered_and_create_invoice(sale_order)

        invoices = sale_order.mapped("order_line.invoice_lines.move_id")
        invoices[-1].button_cancel()
        invoices[-2].action_post()

        self.assertEqual(len(invoices), 5)
        for line in sale_order.order_line:
            self.assertEqual(line.qty_delivered, 5)
            self.assertEqual(line.qty_invoiced, 4)

        invoices[:2].do_merge(keep_references=False)

        invoices = sale_order.mapped("order_line.invoice_lines.move_id")

        self.assertEqual(len(invoices), 4)
        for line in sale_order.order_line:
            self.assertEqual(line.qty_delivered, 5)
            self.assertEqual(line.qty_invoiced, 4)

    def test_callback_different_purchase_order(self):
        if "purchase.order" not in self.env.registry:
            return True
        product_1, product_2 = self.env["product.product"].create(
            [
                {"name": "product 1", "list_price": 5.0, "invoice_policy": "delivery"},
                {"name": "product 2", "list_price": 10.0, "invoice_policy": "delivery"},
            ]
        )
        # Test pre-computes of lines with order
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create({"product_id": product_1.id, "product_qty": 5}),
                    Command.create({"product_id": product_2.id, "product_qty": 2}),
                ],
            }
        )
        purchase_order_2 = purchase_order.copy()

        purchase_order.button_confirm()
        purchase_order_2.button_confirm()

        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order_2)
        self._add_qty_received_and_create_invoice(purchase_order_2)
        self._add_qty_received_and_create_invoice(purchase_order_2)

        inv_purchase_order = purchase_order.mapped("order_line.invoice_lines.move_id")
        inv_purchase_order_2 = purchase_order_2.mapped(
            "order_line.invoice_lines.move_id"
        )
        total_inv_purchase_order = inv_purchase_order | inv_purchase_order_2

        self.assertEqual(len(inv_purchase_order), 3)
        self.assertEqual(len(inv_purchase_order_2), 3)
        self.assertEqual(len(total_inv_purchase_order), 6)
        for line in (purchase_order | purchase_order_2).order_line:
            self.assertEqual(line.qty_received, min(line.product_qty, 3))
            self.assertEqual(line.qty_invoiced, line.qty_received)

        invoices = inv_purchase_order[:1] | inv_purchase_order_2[:1]
        invoices[:2].do_merge(keep_references=False)

        inv_purchase_order = purchase_order.mapped("order_line.invoice_lines.move_id")
        inv_purchase_order_2 = purchase_order_2.mapped(
            "order_line.invoice_lines.move_id"
        )
        total_inv_purchase_order = inv_purchase_order | inv_purchase_order_2

        self.assertEqual(len(inv_purchase_order), 3)
        self.assertEqual(len(inv_purchase_order_2), 3)
        self.assertEqual(len(total_inv_purchase_order), 5)
        for line in (purchase_order | purchase_order_2).order_line:
            self.assertEqual(line.qty_received, min(line.product_qty, 3))
            self.assertEqual(line.qty_invoiced, line.qty_received)

    def test_callback_same_purchase_order(self):
        if "purchase.order" not in self.env.registry:
            return True
        product_1, product_2 = self.env["product.product"].create(
            [
                {"name": "product 1", "list_price": 5.0, "invoice_policy": "delivery"},
                {"name": "product 2", "list_price": 10.0, "invoice_policy": "delivery"},
            ]
        )
        # Test pre-computes of lines with order
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    Command.create({"product_id": product_1.id, "product_qty": 5}),
                    Command.create({"product_id": product_2.id, "product_qty": 5}),
                ],
            }
        )

        purchase_order.button_confirm()
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)
        self._add_qty_received_and_create_invoice(purchase_order)

        invoices = purchase_order.mapped("order_line.invoice_lines.move_id")
        invoices[-1].button_cancel()
        invoices[-2].write({"invoice_date": fields.Date.today()})
        invoices[-2].action_post()

        self.assertEqual(len(invoices), 5)
        for line in purchase_order.order_line:
            self.assertEqual(line.qty_received, 5)
            self.assertEqual(line.qty_invoiced, 4)

        invoices[:2].do_merge(keep_references=False)

        invoices = purchase_order.mapped("order_line.invoice_lines.move_id")

        self.assertEqual(len(invoices), 4)
        for line in purchase_order.order_line:
            self.assertEqual(line.qty_received, 5)
            self.assertEqual(line.qty_invoiced, 4)
