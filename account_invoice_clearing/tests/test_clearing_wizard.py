# Copyright 2023 Moduon Team S.L.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged
from odoo.tools import float_is_zero

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestClearingWizard(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cl_partner = cls.env["res.partner"].create(
            {
                "name": "Clearing Partner",
                "is_company": True,
                "child_ids": [
                    (0, 0, {"name": "Clearing Contact 1", "type": "invoice"}),
                    (0, 0, {"name": "Clearing Contact 2", "type": "invoice"}),
                ],
            }
        )

    def test_unsaved_wizard_without_active_invoices_has_an_empty_preview(self):
        wizard_model = self.env["account.invoice.clearing.wizard"].with_context(
            active_model=False, active_ids=[], active_id=False
        )
        moves = self.env["account.move"]
        counts = (wizard_model.search_count([]), moves.search_count([]))
        defaults = wizard_model.default_get(["invoice_ids", "journal_id", "date"])
        self.assertFalse(defaults.get("invoice_ids"))
        # Initialise the model without saving its required invoice selection.
        wizard = wizard_model.new(defaults)
        wizard._compute_initial_data()
        wizard._onchange_move_type()
        for field in (
            "invoice_ids",
            "move_line_ids",
            "line_ids",
            "company_id",
            "company_currency_id",
            "move_type",
            "commercial_partner_id",
        ):
            self.assertFalse(wizard[field], field)
        self.assertEqual(wizard.amount_to_clear, 0.0)
        self.assertEqual(json.loads(wizard.move_data), [])
        self.assertEqual(json.loads(wizard.preview_move_data)["groups_vals"], [])
        self.assertEqual(
            (wizard_model.search_count([]), moves.search_count([])), counts
        )

    def test_clearing_wizard(self):
        """Test clearing wizard with different move types."""

        def sorted_by_sequence(lines):
            return sorted(lines, key=lambda line: line.sequence)

        t = fields.Date.today()
        t_5 = t + timedelta(days=5)
        t_10 = t + timedelta(days=10)
        move_types = ["out_invoice", "in_invoice"]
        for init_move_type, clearing_move_type in [move_types, move_types[::-1]]:
            with self.subTest(
                init_move_type=init_move_type, clearing_move_type=clearing_move_type
            ):
                init_inv = self.init_invoice(
                    invoice_date=t,
                    move_type=init_move_type,
                    partner=self.cl_partner,
                    amounts=[100, 200],
                    post=True,
                )
                cl_inv_1 = self.init_invoice(
                    invoice_date=t_5,
                    move_type=clearing_move_type,
                    partner=self.cl_partner.child_ids[0],
                    amounts=[100],
                    post=False,
                )
                cl_inv_2 = self.init_invoice(
                    invoice_date=fields.Date.today() + timedelta(days=10),
                    move_type=clearing_move_type,
                    partner=self.cl_partner.child_ids[1],
                    amounts=[200],
                    post=False,
                )
                # Set date maturities
                cl_inv_1.invoice_date_due = t_5
                cl_inv_2.invoice_date_due = t_10
                # Post clearing invoices
                cl_inv_1.action_post()
                cl_inv_2.action_post()
                # Create wizard
                cw_action = init_inv.action_open_invoice_clearing_wizard()
                wizard = self.env[cw_action["res_model"]].browse(cw_action["res_id"])
                # Test Action: Unlink Lines
                wizard._action_unlink_lines()
                self.assertFalse(wizard.line_ids)
                # Test Action: Add Lines
                wizard._action_add_lines()
                self.assertTrue(wizard.line_ids)
                # Test Action: Sort Lines by Date Due (lines changes sequence)
                wizard.action_sort_by_date_due()  # Initialize with some order
                slines_0 = sorted_by_sequence(wizard.line_ids)
                wizard.action_sort_by_date_due()
                slines_1 = sorted_by_sequence(wizard.line_ids)
                self.assertNotEqual(slines_0, slines_1)
                self.assertEqual(slines_0, slines_1[::-1])
                wizard.action_sort_by_date_due()
                slines_2 = sorted_by_sequence(wizard.line_ids)
                self.assertNotEqual(slines_1, slines_2)
                self.assertEqual(slines_1, slines_2[::-1])
                # Test Action: Sort Lines by Amount Residual (lines changes sequence)
                wizard.action_sort_by_residual()  # Initialize with some order
                slines_0 = sorted_by_sequence(wizard.line_ids)
                wizard.action_sort_by_residual()
                slines_1 = sorted_by_sequence(wizard.line_ids)
                self.assertNotEqual(slines_0, slines_1)
                self.assertEqual(slines_0, slines_1[::-1])
                wizard.action_sort_by_residual()
                slines_2 = sorted_by_sequence(wizard.line_ids)
                self.assertNotEqual(slines_1, slines_2)
                self.assertEqual(slines_1, slines_2[::-1])
                # Test Action: Fill Amount to Clear
                wizard.action_fill_amount_to_clear()
                wizard.invalidate_recordset()
                self.assertTrue(
                    float_is_zero(
                        wizard.amount_to_clear,
                        precision_rounding=wizard.company_currency_id.rounding,
                    )
                )
                # Test Action: Reset Lines
                wizard.action_reset_lines()
                wizard.invalidate_recordset()
                self.assertTrue(
                    not float_is_zero(
                        wizard.amount_to_clear,
                        precision_rounding=wizard.company_currency_id.rounding,
                    )
                )
                # Create moves
                wizard.action_fill_amount_to_clear()
                wizard.invalidate_recordset()
                wizard.button_confirm()
                self.assertEqual(init_inv.payment_state, "paid")
                self.assertEqual(cl_inv_1.payment_state, "paid")
                self.assertEqual(cl_inv_2.payment_state, "paid")

    def test_account_types(self):
        aicw_model = self.env["account.invoice.clearing.wizard"]
        # For lines to clear
        self.assertEqual(
            "liability_payable",
            aicw_model._get_account_type_from_move_type(
                "in_invoice", is_counterpart=False
            ),
        )
        self.assertEqual(
            "asset_receivable",
            aicw_model._get_account_type_from_move_type(
                "out_invoice", is_counterpart=False
            ),
        )
        # For counterpart lines
        self.assertEqual(
            "asset_receivable",
            aicw_model._get_account_type_from_move_type(
                "in_invoice", is_counterpart=True
            ),
        )
        self.assertEqual(
            "liability_payable",
            aicw_model._get_account_type_from_move_type(
                "out_invoice", is_counterpart=True
            ),
        )

    def test_incompatible_invoice_selections_are_refused(self):
        other_partner = self.env["res.partner"].create(
            {"name": "Fabricated other company", "is_company": True}
        )
        invoice = self.init_invoice(
            "out_invoice", partner=self.cl_partner, amounts=[50], post=True
        )
        different_partner = self.init_invoice(
            "out_invoice", partner=other_partner, amounts=[50], post=True
        )
        different_type = self.init_invoice(
            "in_invoice", partner=self.cl_partner, amounts=[50], post=True
        )
        for other, reason in (
            (different_partner, "Invoices must be from the same commercial partner"),
            (different_type, "Invoices must be of the same type"),
        ):
            with (
                self.subTest(reason=reason),
                self.assertRaisesRegex(ValidationError, reason),
                self.env.cr.savepoint(),
            ):
                (invoice + other).action_open_invoice_clearing_wizard()
        contact_invoice = self.init_invoice(
            "out_invoice", partner=self.cl_partner.child_ids[0], amounts=[50], post=True
        )
        action = (invoice + contact_invoice).action_open_invoice_clearing_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.invoice_ids, invoice + contact_invoice)

    def test_empty_clearing_can_be_sorted_then_refreshed_with_a_counterpart(self):
        for target_type, counterpart_type, sign in (
            ("out_invoice", "in_invoice", 1),
            ("in_invoice", "out_invoice", -1),
        ):
            with self.subTest(target_type=target_type):
                partner = self.env["res.partner"].create(
                    {"name": "Clearing refresh partner"}
                )
                target = self.init_invoice(
                    target_type, partner=partner, amounts=[100], post=False
                )
                target.invoice_line_ids.tax_ids = False
                target.action_post()
                action = target.action_open_invoice_clearing_wizard()
                wizard = self.env[action["res_model"]].browse(action["res_id"])
                before_count = self.env["account.move"].search_count([])
                self.assertFalse(wizard.line_ids)
                self.assertEqual(wizard.move_data, "[]")
                self.assertEqual(
                    json.loads(wizard.preview_move_data)["groups_vals"], []
                )
                self.assertEqual(wizard.amount_to_clear, sign * 100)
                for sort in (
                    wizard.action_sort_by_date_due,
                    wizard.action_sort_by_residual,
                ):
                    self.assertEqual(sort()["res_id"], wizard.id)
                    self.assertFalse(wizard.line_ids)
                    self.assertEqual(target.amount_residual, 100)
                    self.assertEqual(
                        self.env["account.move"].search_count([]), before_count
                    )
                counterpart = self.init_invoice(
                    counterpart_type, partner=partner, amounts=[60], post=False
                )
                counterpart.invoice_line_ids.tax_ids = False
                counterpart.action_post()
                wizard.action_reset_lines()
                self.assertEqual(len(wizard.line_ids), 1)
                line = wizard.line_ids
                self.assertEqual(line.invoice_id, counterpart)
                original = (line.id, line.sequence, line.amount_to_clear)
                for sort in (
                    wizard.action_sort_by_date_due,
                    wizard.action_sort_by_residual,
                ):
                    self.assertEqual(sort()["res_id"], wizard.id)
                    self.assertEqual(
                        (wizard.line_ids.id, line.sequence, line.amount_to_clear),
                        original,
                    )
                wizard.action_fill_amount_to_clear()
                self.assertEqual(line.amount_to_clear, -sign * 60)
                # The returned action reopens the form in a fresh RPC/cache.
                wizard.invalidate_recordset(["amount_to_clear"])
                self.assertEqual(wizard.amount_to_clear, sign * 40)
                wizard.button_confirm()
                self.assertEqual(target.amount_residual, 40)
                self.assertEqual(counterpart.amount_residual, 0)

    def test_clearing_rejects_invoices_from_different_companies(self):
        other_company = self.setup_other_company()["company"]
        companies = self.env.company | other_company
        self.env.user.company_ids = companies
        self.env = self.env(
            context=dict(self.env.context, allowed_company_ids=companies.ids)
        )
        invoices = self.env["account.move"]
        for company in companies:
            invoice = self.init_invoice(
                "out_invoice",
                partner=self.cl_partner,
                company=company,
                amounts=[50],
                post=False,
            )
            invoice.invoice_line_ids.tax_ids = False
            invoice.action_post()
            invoices |= invoice
        before_count = self.env["account.move"].search_count([])
        with (
            self.assertRaisesRegex(
                ValidationError, "Invoices must belong to the same company"
            ),
            self.env.cr.savepoint(),
        ):
            invoices.action_open_invoice_clearing_wizard()
        self.assertEqual([invoice.amount_residual for invoice in invoices], [50, 50])
        self.assertEqual(self.env["account.move"].search_count([]), before_count)

    def test_signed_counterpart_residual_is_an_exact_upper_bound(self):
        for target_type, counterpart_type in (
            ("out_invoice", "in_invoice"),
            ("in_invoice", "out_invoice"),
        ):
            with self.subTest(target_type=target_type):
                target = self.init_invoice(
                    target_type, partner=self.cl_partner, amounts=[100], post=True
                )
                counterpart = self.init_invoice(
                    counterpart_type, partner=self.cl_partner, amounts=[50], post=True
                )
                action = target.action_open_invoice_clearing_wizard()
                wizard = self.env[action["res_model"]].browse(action["res_id"])
                line = wizard.line_ids.filtered(
                    lambda record, counterpart=counterpart: record.invoice_id
                    == counterpart
                )
                self.assertEqual(len(line), 1)
                residual = line.amount_residual
                self.assertTrue(residual)
                self.assertEqual(residual > 0, counterpart_type == "out_invoice")
                line.amount_to_clear = residual
                self.assertEqual(line.amount_to_clear, residual)
                excess = (
                    residual
                    + (1 if residual > 0 else -1) * line.company_currency_id.rounding
                )
                with (
                    self.assertRaisesRegex(
                        ValidationError,
                        "Amount to clear cannot be greater than residual amount",
                    ),
                    self.env.cr.savepoint(),
                ):
                    line.amount_to_clear = excess
                self.assertEqual(line.amount_to_clear, residual)

    def test_use_action_tops_up_a_partial_allocation_in_both_directions(self):
        for target_type, counterpart_type, sign in (
            ("out_invoice", "in_invoice", 1),
            ("in_invoice", "out_invoice", -1),
        ):
            with self.subTest(target_type=target_type):
                target = self.init_invoice(
                    target_type, partner=self.cl_partner, amounts=[100], post=False
                )
                counterpart = self.init_invoice(
                    counterpart_type,
                    partner=self.cl_partner,
                    amounts=[150],
                    post=False,
                )
                (target | counterpart).invoice_line_ids.tax_ids = False
                (target | counterpart).action_post()
                action = target.action_open_invoice_clearing_wizard()
                wizard = self.env[action["res_model"]].browse(action["res_id"])
                line = wizard.line_ids.filtered(
                    lambda item, counterpart=counterpart: item.invoice_id == counterpart
                )
                self.assertEqual(len(line), 1)
                self.assertEqual(line.amount_residual, -sign * 150)
                line.amount_to_clear = -sign * 40
                self.assertEqual(wizard.amount_to_clear, sign * 60)
                self.assertTrue(line.can_use_line)
                line.action_use_all_amount_residual()
                wizard.invalidate_recordset()
                line.invalidate_recordset()
                self.assertEqual(line.amount_to_clear, -sign * 100)
                self.assertEqual(wizard.amount_to_clear, 0)
                self.assertFalse(line.can_use_line)
                line.action_use_all_amount_residual()
                self.assertEqual(line.amount_to_clear, -sign * 100)

    def test_use_caps_at_residual_and_auto_fill_preserves_existing_allocations(self):
        for target_type, counterpart_type, sign in (
            ("out_invoice", "in_invoice", 1),
            ("in_invoice", "out_invoice", -1),
        ):
            with self.subTest(target_type=target_type):
                partner = self.env["res.partner"].create(
                    {"name": "Fabricated capped clearing partner", "is_company": True}
                )
                target = self.init_invoice(
                    target_type, partner=partner, amounts=[100], post=False
                )
                counterparts = self.env["account.move"]
                for amount in (60, 150, 40):
                    counterparts |= self.init_invoice(
                        counterpart_type, partner=partner, amounts=[amount], post=False
                    )
                (target | counterparts).invoice_line_ids.tax_ids = False
                (target | counterparts).action_post()
                action = target.action_open_invoice_clearing_wizard()
                wizard = self.env[action["res_model"]].browse(action["res_id"])
                lines = self.env["account.invoice.clearing.lines.wizard"]
                for sequence, counterpart in enumerate(counterparts, start=10):
                    line = wizard.line_ids.filtered(
                        lambda item, counterpart=counterpart: item.invoice_id
                        == counterpart
                    )
                    self.assertEqual(len(line), 1)
                    line.sequence = sequence
                    lines |= line
                original_ids = set(wizard.line_ids.ids)
                wizard._action_add_lines()
                self.assertEqual(set(wizard.line_ids.ids), original_ids)
                self.assertEqual(wizard._get_remaining_amount_to_clear(), sign * 100)
                lines[0].action_use_all_amount_residual()
                wizard.invalidate_recordset()
                self.assertEqual(lines[0].amount_to_clear, -sign * 60)
                self.assertEqual(wizard.amount_to_clear, sign * 40)
                self.assertEqual(wizard._get_remaining_amount_to_clear(), sign * 40)
                for _ in range(2):
                    wizard.action_fill_amount_to_clear()
                    wizard.invalidate_recordset()
                    self.assertEqual(
                        lines.mapped("amount_to_clear"), [-sign * 60, -sign * 40, 0]
                    )
                    self.assertEqual(wizard.amount_to_clear, 0)
                    self.assertEqual(wizard._get_remaining_amount_to_clear(), 0)
                wizard.button_confirm()
                self.assertEqual(target.amount_residual, 0)
                self.assertEqual(counterparts.mapped("amount_residual"), [0, 110, 40])
                self.assertEqual(
                    lines.mapped("move_line_id.amount_residual"),
                    [0, -sign * 110, -sign * 40],
                )

    def test_preview_and_confirmation_distribute_limited_allocations(self):
        for target_type, counterpart_type in (
            ("out_invoice", "in_invoice"),
            ("in_invoice", "out_invoice"),
        ):
            with self.subTest(target_type=target_type):
                partner = self.env["res.partner"].create(
                    {"name": "Fabricated preview clearing partner", "is_company": True}
                )
                targets = self.env["account.move"]
                for _ in range(3):
                    targets |= self.init_invoice(
                        target_type, partner=partner, amounts=[100], post=False
                    )
                counterparts = self.env["account.move"]
                for amount in (150, 10):
                    counterparts |= self.init_invoice(
                        counterpart_type, partner=partner, amounts=[amount], post=False
                    )
                (targets | counterparts).invoice_line_ids.tax_ids = False
                (targets | counterparts).action_post()
                action = targets.action_open_invoice_clearing_wizard()
                wizard = self.env[action["res_model"]].browse(action["res_id"])
                for sequence, counterpart in enumerate(counterparts, start=10):
                    line = wizard.line_ids.filtered(
                        lambda item, counterpart=counterpart: item.invoice_id
                        == counterpart
                    )
                    self.assertEqual(len(line), 1)
                    line.sequence = sequence
                    line.amount_to_clear = line.amount_residual
                wizard.write(
                    {
                        "move_name": "Fabricated clearing batch",
                        "move_line_prefix": "Fabricated clearing allocation",
                    }
                )
                before_count = self.env["account.move"].search_count([])
                wizard.invalidate_recordset()
                ordered_targets = [line.move_id for line in wizard.move_line_ids]
                self.assertEqual(len(ordered_targets), 3)
                self.assertEqual(
                    {move.id for move in ordered_targets}, set(targets.ids)
                )
                move_data = json.loads(wizard.move_data)
                preview = json.loads(wizard.preview_move_data)
                self.assertEqual(len(move_data), 2)
                self.assertEqual(len(preview["groups_vals"]), 2)
                for move, amount in zip(move_data, (100, 60), strict=True):
                    self.assertEqual(move["ref"], "<Move Name>")
                    self.assertEqual(
                        sum(command[2]["debit"] for command in move["line_ids"]), amount
                    )
                    self.assertEqual(
                        sum(command[2]["credit"] for command in move["line_ids"]),
                        amount,
                    )
                    self.assertTrue(
                        all(
                            command[2]["name"].startswith("<Move Line Prefix> - ")
                            for command in move["line_ids"]
                        )
                    )
                self.assertEqual(
                    self.env["account.move"].search_count([]), before_count
                )
                self.assertEqual(targets.mapped("amount_residual"), [100, 100, 100])
                self.assertEqual(counterparts.mapped("amount_residual"), [150, 10])
                result = wizard.button_confirm()
                self.assertEqual(result["res_model"], "account.move")
                self.assertEqual(result["view_mode"], "list,form")
                entries = self.env["account.move"].search(result["domain"])
                self.assertEqual(len(entries), 2)
                self.assertEqual(entries.mapped("state"), ["posted", "posted"])
                self.assertEqual(
                    entries.mapped("ref"), ["Fabricated clearing batch"] * 2
                )
                self.assertTrue(
                    all(
                        line.name.startswith("Fabricated clearing allocation - ")
                        for line in entries.line_ids
                    )
                )
                self.assertEqual(
                    [move.amount_residual for move in ordered_targets], [0, 40, 100]
                )
                self.assertEqual(counterparts.mapped("amount_residual"), [0, 0])
