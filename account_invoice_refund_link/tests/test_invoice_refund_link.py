# Copyright 2016 Tecnativa - Antonio Espinosa
# Copyright 2014-2023 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command

from odoo.addons.base.tests.common import BaseCommon

from .. import post_init_hook


class TestInvoiceRefundLinkBase(BaseCommon):
    is_modify = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
                mail_notrack=True,
                no_reset_password=True,
                tracking_disable=True,
            )
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test partner"})
        default_line_account = cls.env["account.account"].create(
            {
                "name": "TESTACC",
                "code": "TESTACC",
                "account_type": "income",
                "company_ids": [Command.link(cls.env.user.company_id.id)],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Journal 1",
                "code": "J1",
                "type": "sale",
                "company_id": cls.env.user.company_id.id,
            }
        )
        cls.invoice_lines = [
            (
                0,
                False,
                {
                    "name": "Test section",
                    "display_type": "line_section",
                },
            ),
            (
                0,
                False,
                {
                    "name": "Test description #1",
                    "account_id": default_line_account.id,
                    "quantity": 1.0,
                    "price_unit": 100.0,
                },
            ),
            (
                0,
                False,
                {
                    "name": "Test description #2",
                    "account_id": default_line_account.id,
                    "quantity": 2.0,
                    "price_unit": 25.0,
                },
            ),
        ]
        cls.invoice = cls.env["account.move"].create(
            {
                "partner_id": cls.partner.id,
                "move_type": "out_invoice",
                "invoice_line_ids": cls.invoice_lines,
            }
        )
        cls.invoice.action_post()
        cls.refund_reason = "The refund reason"
        cls.env["account.move.reversal"].with_context(
            active_ids=cls.invoice.ids, active_model="account.move"
        ).create(
            {
                "reason": cls.refund_reason,
                "journal_id": cls.journal.id,
            }
        ).reverse_moves(is_modify=cls.is_modify)

    def _test_refund_link(self):
        self.assertTrue(self.invoice.refund_invoice_ids)
        refund = self.invoice.refund_invoice_ids[0]
        ref = f"Reversal of: {self.invoice.name}, {self.refund_reason}"
        self.assertEqual(refund.ref, ref)
        self.assertEqual(len(self.invoice.invoice_line_ids), len(self.invoice_lines))
        self.assertEqual(len(refund.invoice_line_ids), len(self.invoice_lines))
        # We're checking only the 2nd and 3rd lines because the first is a line section
        self.assertTrue(refund.invoice_line_ids[1].origin_line_id)
        self.assertEqual(
            self.invoice.invoice_line_ids[1], refund.invoice_line_ids[1].origin_line_id
        )
        self.assertTrue(refund.invoice_line_ids[2].origin_line_id)
        self.assertEqual(
            self.invoice.invoice_line_ids[2], refund.invoice_line_ids[2].origin_line_id
        )


class TestInvoiceRefundLink(TestInvoiceRefundLinkBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_post_init_hook(self):
        self.assertTrue(self.invoice.refund_invoice_ids)
        refund = self.invoice.refund_invoice_ids[0]
        refund.invoice_line_ids.write({"origin_line_id": False})
        self.assertFalse(refund.mapped("invoice_line_ids.origin_line_id"))
        post_init_hook(self.env)
        self.refund_reason = "The refund reason"
        self._test_refund_link()

    def test_post_init_hook_matches_edited_refund_lines_once(self):
        products = self.env["product.product"].create(
            [
                {"name": name, "type": "service"}
                for name in (
                    "Sample first service",
                    "Sample second service",
                    "Sample extra service",
                )
            ]
        )
        account = self.invoice.invoice_line_ids.filtered("account_id")[0].account_id

        def line_values(sequence, product, name, quantity, price):
            return {
                "sequence": sequence,
                "product_id": product.id if product else False,
                "name": name,
                "quantity": quantity,
                "price_unit": price,
                "account_id": account.id,
                "tax_ids": [Command.clear()],
            }

        invoice = self.env["account.move"].create(
            {
                "partner_id": self.partner.id,
                "move_type": "out_invoice",
                "invoice_line_ids": [
                    Command.create(
                        line_values(10, products[0], "First service", 2, 100)
                    ),
                    Command.create(
                        line_values(20, products[1], "Second service", 1, 50)
                    ),
                ],
            }
        )
        invoice.action_post()
        self.env["account.move.reversal"].with_context(
            active_ids=invoice.ids, active_model="account.move"
        ).create(
            {"reason": "Sample partial refund", "journal_id": self.journal.id}
        ).reverse_moves(is_modify=False)
        refund = invoice.refund_invoice_ids
        refund.ensure_one()
        self.assertEqual(refund.state, "draft")
        refund.invoice_line_ids = [
            Command.clear(),
            Command.create(line_values(10, products[2], "Additional service", 1, 10)),
            Command.create(
                line_values(20, products[1], "Edited second service", 1, 25)
            ),
            Command.create(line_values(30, False, "First service", 1, 100)),
            Command.create(
                line_values(40, products[0], "Surplus first service", 0.1, 50)
            ),
        ]
        refund.invoice_line_ids.write({"origin_line_id": False})
        lines = refund.invoice_line_ids
        self.assertEqual(lines.mapped("sequence"), [10, 20, 30, 40])
        business_fields = [
            "sequence",
            "product_id",
            "name",
            "quantity",
            "price_unit",
            "price_subtotal",
        ]
        original_values = lines.read(business_fields)
        expected_origins = [
            False,
            invoice.invoice_line_ids[1].id,
            invoice.invoice_line_ids[0].id,
            False,
        ]
        for _ in range(2):
            post_init_hook(self.env)
            lines.invalidate_recordset([*business_fields, "origin_line_id"])
            refund.invalidate_recordset(["amount_total", "state"])
            self.assertEqual(
                [line.origin_line_id.id for line in lines], expected_origins
            )
            self.assertEqual(lines.read(business_fields), original_values)
            self.assertEqual(refund.invoice_line_ids, lines)
            self.assertEqual(refund.state, "draft")
            self.assertAlmostEqual(refund.amount_total, 140)
            self.assertEqual(invoice.state, "posted")
            self.assertAlmostEqual(invoice.amount_total, 250)
            self.assertEqual(invoice.refund_invoice_ids, refund)

        refund.invoice_line_ids = [Command.clear()]
        post_init_hook(self.env)
        refund.invalidate_recordset(["invoice_line_ids", "amount_total", "state"])
        self.assertFalse(refund.invoice_line_ids)
        self.assertEqual(refund.state, "draft")
        self.assertAlmostEqual(refund.amount_total, 0)
        self.assertEqual(invoice.refund_invoice_ids, refund)

    def test_refund_link(self):
        self._test_refund_link()

    def test_invoice_copy(self):
        refund = self.invoice.refund_invoice_ids[0]
        self.invoice.copy()
        self.assertEqual(
            refund.invoice_line_ids.origin_line_id, self.invoice.invoice_line_ids
        )

    def test_refund_copy(self):
        refund = self.invoice.refund_invoice_ids[0]
        refund.copy()
        self.assertEqual(
            self.invoice.invoice_line_ids, refund.invoice_line_ids.origin_line_id
        )


class TestInvoiceRefundNoModifyLink(TestInvoiceRefundLinkBase):
    is_modify = False

    def test_refund_link(self):
        self._test_refund_link()


class TestInvoiceRefundModifyLink(TestInvoiceRefundLinkBase):
    is_modify = True

    def test_refund_link(self):
        self._test_refund_link()
