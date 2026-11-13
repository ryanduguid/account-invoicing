# Copyright 2019 Tecnativa - David Vidal
# Copyright 2020 Tecnativa - Pedro M. Baeza
# Copyright 2021 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import exceptions
from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_global_discount import _pre_init_global_discount_fields


@tagged("post_install", "-at_install")
class TestGlobalDiscount(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,
                test_account_global_discount=True,
            )
        )
        cls.env.user.group_ids |= cls.env.ref(
            "base_global_discount.group_global_discount"
        )
        cls.account = cls.company_data["default_account_revenue"]
        cls.global_discount_obj = cls.env["global.discount"]
        cls.global_discount_1 = cls.global_discount_obj.create(
            {
                "name": "Test Discount 1",
                "discount_scope": "sale",
                "discount": 20,
                "account_id": cls.account.id,
                "sequence": 3,
            }
        )
        cls.global_discount_2 = cls.global_discount_obj.create(
            {
                "name": "Test Discount 2",
                "discount_scope": "purchase",
                "discount": 30,
                "account_id": cls.account.id,
                "sequence": 2,
            }
        )
        cls.global_discount_3 = cls.global_discount_obj.create(
            {
                "name": "Test Discount 3",
                "discount_scope": "purchase",
                "discount": 50,
                "account_id": cls.account.id,
                "sequence": 1,
            }
        )
        cls.partner_1 = cls.env["res.partner"].create(
            {
                "name": "Mr. Odoo",
            }
        )
        cls.partner_2 = cls.env["res.partner"].create(
            {
                "name": "Mrs. Odoo",
            }
        )
        cls.partner_2.supplier_global_discount_ids = cls.global_discount_2
        cls.tax = cls.tax_purchase_a
        cls.tax.amount = 15
        cls.tax_0 = cls.tax_purchase_b
        cls.tax_0.amount = 0
        cls.product_3 = cls.env["product.product"].create(
            {
                "name": "Test Product 3",
                "type": "service",
                "bypass_global_discount": True,
            }
        )
        cls.invoice_line = cls.env["account.move.line"]
        cls.invoice = (
            cls.env["account.move"]
            .with_context(default_move_type="in_invoice")
            .create(
                {
                    "partner_id": cls.partner_1.id,
                    "ref": "Test global discount",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "Line 1",
                                "price_unit": 200.0,
                                "quantity": 1,
                                "tax_ids": [Command.set(cls.tax.ids)],
                            },
                        ),
                        Command.create(
                            {
                                "name": "Line 2",
                                "product_id": cls.product_3.id,
                                "price_unit": 200.0,
                                "quantity": 1,
                                "tax_ids": [Command.set(cls.tax_0.ids)],
                            },
                        ),
                    ],
                }
            )
        )

    def test_pre_init_preserves_existing_discounted_invoice(self):
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_2)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -60)
        self.assertAlmostEqual(self.invoice.amount_untaxed_before_global_discounts, 400)
        invoice_fields = [
            "amount_global_discount",
            "amount_untaxed_before_global_discounts",
            "amount_untaxed",
            "amount_tax",
            "amount_total",
            "global_discount_ids",
            "invoice_global_discount_ids",
            "invoice_line_ids",
            "state",
        ]
        line_fields = ["quantity", "price_unit", "discount", "tax_ids", "balance"]
        lines = self.invoice.invoice_line_ids
        self.invoice.flush_recordset()
        lines.flush_recordset()
        before_invoice = self.invoice.read(invoice_fields)
        before_lines = lines.read(line_fields)
        for _ in range(2):
            _pre_init_global_discount_fields(self.env)
            self.invoice.invalidate_recordset(invoice_fields)
            lines.invalidate_recordset(line_fields)
            self.assertEqual(self.invoice.read(invoice_fields), before_invoice)
            self.assertEqual(lines.read(line_fields), before_lines)

    def test_discount_removal_preserves_sections_and_restores_totals(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_1.id,
                "invoice_line_ids": [
                    Command.create(
                        {"display_type": "line_section", "name": "Services"}
                    ),
                    Command.create(
                        {"display_type": "line_note", "name": "Agreed work"}
                    ),
                    *(
                        Command.create(
                            {
                                "name": name,
                                "price_unit": amount,
                                "quantity": 1,
                                "tax_ids": [Command.set(self.tax.ids)],
                            }
                        )
                        for name, amount in (("Preparation", 200), ("Review", 100))
                    ),
                ],
            }
        )
        original_lines = invoice.invoice_line_ids
        with Form(invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_2)
        self.assertAlmostEqual(invoice.amount_untaxed, 210)
        self.assertAlmostEqual(invoice.amount_tax, 31.5)
        self.assertAlmostEqual(invoice.amount_total, 241.5)
        self.assertAlmostEqual(invoice.amount_global_discount, -90)
        self.assertEqual(len(invoice.invoice_global_discount_ids), 1)
        self.assertFalse(original_lines - invoice.invoice_line_ids)
        self.assertCountEqual(
            original_lines.mapped("display_type"),
            ["line_section", "line_note", "product", "product"],
        )

        with Form(invoice) as invoice_form:
            invoice_form.global_discount_ids.clear()
        self.assertAlmostEqual(invoice.amount_untaxed, 300)
        self.assertAlmostEqual(invoice.amount_tax, 45)
        self.assertAlmostEqual(invoice.amount_total, 345)
        self.assertAlmostEqual(invoice.amount_global_discount, 0)
        self.assertFalse(invoice.invoice_global_discount_ids)
        self.assertCountEqual(invoice.invoice_line_ids.ids, original_lines.ids)

    def test_taxed_bypassed_product_keeps_its_full_amount_when_discounted(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_1.id,
                "invoice_date": self.invoice.date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Sample bypassed service",
                            "product_id": self.product_3.id,
                            "account_id": self.account.id,
                            "price_unit": 200,
                            "quantity": 1,
                            "tax_ids": [Command.set(self.tax.ids)],
                        }
                    )
                ],
            }
        )
        original_lines = invoice.invoice_line_ids
        with Form(invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_2)
        self.assertEqual(invoice.global_discount_ids, self.global_discount_2)
        self.assertFalse(invoice.invoice_global_discount_ids)
        self.assertEqual(invoice.invoice_line_ids, original_lines)
        self.assertAlmostEqual(invoice.amount_global_discount, 0)
        self.assertAlmostEqual(invoice.amount_untaxed, 200)
        self.assertAlmostEqual(invoice.amount_tax, 30)
        self.assertAlmostEqual(invoice.amount_total, 230)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        self.assertFalse(invoice.invoice_global_discount_ids)
        self.assertAlmostEqual(sum(invoice.line_ids.mapped("balance")), 0)

    def test_01_global_invoice_succesive_discounts(self):
        """Add global discounts to the invoice"""
        invoice_tax_line = self.invoice.line_ids.filtered("tax_line_id")
        # import pdb; pdb.set_trace()
        self.assertAlmostEqual(self.invoice.amount_total, 430)
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 200.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 30.0)
        # Global discounts are applied to the base and taxes are recomputed:
        # 200 - 50% (global disc. 3) =  100
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.clear()
            invoice_form.global_discount_ids.add(self.global_discount_3)
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 1)
        precision = self.env["decimal.precision"].precision_get("Discount")
        self.assertEqual(
            self.invoice.invoice_global_discount_ids.discount_display,
            "-50.{}%".format("0" * precision),
        )
        invoice_tax_line = self.invoice.line_ids.filtered("tax_line_id")
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 100.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 15.0)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 300.0)
        self.assertAlmostEqual(self.invoice.amount_total, 315.0)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -100.0)
        # Global discounts are computed succecively:
        # 200 - 50% (global disc. 1) =  100
        # 100  - 30% (global disc. 2) =  70
        # The global discounts amount is then 200 - 70 = 130
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_2)
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 2)
        invoice_tax_line = self.invoice.line_ids.filtered("tax_line_id")
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 70.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 10.5)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 270.0)
        self.assertAlmostEqual(self.invoice.amount_total, 280.5)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -130.0)
        # Line discounts apply before global ones so:
        # 200 - 20% (line discount)  = 160
        # 160 - 50% (global disc. 1) =  80
        # 80  - 30% (global disc. 2) =  56
        # The global discounts amount is then 160 - 56 = 104
        with Form(self.invoice) as invoice_form:
            with invoice_form.invoice_line_ids.edit(0) as line_form:
                if "discount1" in self.env["account.move.line"]._fields:
                    line_form.discount1 = 20
                else:
                    line_form.discount = 20
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 2)
        invoice_tax_line = self.invoice.line_ids.filtered("tax_line_id")
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 56.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 8.4)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 256.0)
        self.assertAlmostEqual(self.invoice.amount_total, 264.4)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -104.0)

    def test_02_global_invoice_discounts_from_partner(self):
        """Change the partner and his global discounts go to the invoice"""
        invoice_tax_line = self.invoice.line_ids.filtered("tax_line_id")
        self.assertAlmostEqual(self.invoice.amount_total, 430)
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 200.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 30.0)
        # When we change the parter, his global discounts are fetched depending
        # on the type of the invoice. In this case, we fetch the supplier
        # global discounts
        with Form(self.invoice) as invoice_form:
            invoice_form.partner_id = self.partner_2
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, 140.0)
        self.assertAlmostEqual(invoice_tax_line.balance, 21.0)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 340.0)
        self.assertAlmostEqual(self.invoice.amount_total, 361.0)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -60.0)

    def test_03_multiple_taxes_multi_line(self):
        tax2 = self.tax.copy(default={"amount": 20.0, "name": "Tax 2"})
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_1)
            with invoice_form.invoice_line_ids.new() as line_form:
                line_form.name = "Line 2"
                line_form.price_unit = 100.0
                line_form.quantity = 1
                line_form.tax_ids.clear()
                line_form.tax_ids.add(tax2)
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 2)
        discount_tax_15 = self.invoice.invoice_global_discount_ids.filtered(
            lambda x: x.tax_ids == self.tax
        )
        discount_tax_20 = self.invoice.invoice_global_discount_ids.filtered(
            lambda x: x.tax_ids == tax2
        )
        self.assertAlmostEqual(discount_tax_15.discount_amount, 40)
        self.assertAlmostEqual(discount_tax_20.discount_amount, 20)
        tax_line_15 = self.invoice.line_ids.filtered(
            lambda x: x.tax_line_id == self.tax
        )
        tax_line_20 = self.invoice.line_ids.filtered(lambda x: x.tax_line_id == tax2)
        self.assertAlmostEqual(tax_line_15.tax_base_amount, 160)
        self.assertAlmostEqual(tax_line_15.balance, 24)
        self.assertAlmostEqual(tax_line_20.tax_base_amount, 80.0)
        self.assertAlmostEqual(tax_line_20.balance, 16)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 440.0)
        self.assertAlmostEqual(self.invoice.amount_total, 480)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -60.0)
        # Check journal items validity
        lines = self.invoice.line_ids
        line_15 = lines.filtered(
            lambda x: x.invoice_global_discount_id and x.tax_ids == self.tax
        )
        self.assertAlmostEqual(line_15.credit, 40)
        line_20 = lines.filtered(
            lambda x: x.invoice_global_discount_id and x.tax_ids == tax2
        )
        self.assertAlmostEqual(line_20.credit, 20)

    def test_04_multiple_taxes_same_line(self):
        tax2 = self.tax.copy(
            default={"amount": -20.0, "name": "Tax 2"}
        )  # negative for testing more use cases
        with Form(self.invoice.with_context(check_move_validity=False)) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_1)
            with invoice_form.invoice_line_ids.edit(0) as line_form:
                line_form.tax_ids.add(tax2)
        # Global discounts are applied to the base and taxes are recomputed:
        # 300 - 20% (global disc. 1) =  240
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 1)
        self.assertAlmostEqual(
            self.invoice.invoice_global_discount_ids.discount_amount, 40
        )
        self.assertEqual(
            self.invoice.invoice_global_discount_ids.tax_ids, self.tax + tax2
        )
        tax_line_15 = self.invoice.line_ids.filtered(
            lambda x: x.tax_line_id == self.tax
        )
        tax_line_20 = self.invoice.line_ids.filtered(lambda x: x.tax_line_id == tax2)
        self.assertAlmostEqual(tax_line_15.tax_base_amount, 160)
        self.assertAlmostEqual(tax_line_15.balance, 24)
        self.assertAlmostEqual(tax_line_20.tax_base_amount, 160.0)
        self.assertAlmostEqual(tax_line_20.balance, -32)
        self.assertAlmostEqual(self.invoice.amount_untaxed, 360.0)
        self.assertAlmostEqual(self.invoice.amount_total, 352)
        self.assertAlmostEqual(self.invoice.amount_global_discount, -40.0)

    def test_05_incompatible_taxes(self):
        # Line 1 with tax and tax2
        # Line 2 with only tax2
        tax2 = self.tax.copy(
            default={"amount": -20.0, "name": "Tax 2"}
        )  # negative for testing more use cases
        with self.assertRaises(exceptions.UserError):
            with Form(self.invoice) as invoice_form:
                invoice_form.global_discount_ids.add(self.global_discount_1)
                with invoice_form.invoice_line_ids.new() as line_form:
                    line_form.name = "Line 2"
                    line_form.price_unit = 100.0
                    line_form.quantity = 1
                    line_form.tax_ids.clear()
                    line_form.tax_ids.add(self.tax)
                    line_form.tax_ids.add(tax2)

    def test_06_no_taxes(self):
        with self.assertRaises(exceptions.UserError):
            with Form(self.invoice) as invoice_form:
                invoice_form.global_discount_ids.add(self.global_discount_1)
                with invoice_form.invoice_line_ids.edit(0) as line_form:
                    line_form.tax_ids.clear()

    def test_07_line_with_tax_0(self):
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_1)
            with invoice_form.invoice_line_ids.edit(0) as line_form:
                line_form.tax_ids.clear()
                line_form.tax_ids.add(self.tax_0)
        discounts = self.invoice.invoice_global_discount_ids
        self.assertEqual(len(discounts), 1)
        self.assertAlmostEqual(discounts.discount_amount, 40)

    def test_08_line2_with_tax_0(self):
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_1)
            with invoice_form.invoice_line_ids.new() as line_form:
                line_form.name = "Line 2"
                line_form.price_unit = 100.0
                line_form.quantity = 1
                line_form.tax_ids.clear()
                line_form.tax_ids.add(self.tax_0)
        self.assertEqual(len(self.invoice.invoice_global_discount_ids), 2)
        discount_tax_15 = self.invoice.invoice_global_discount_ids.filtered(
            lambda x: x.tax_ids == self.tax
        )
        self.assertAlmostEqual(discount_tax_15.discount_amount, 40)
        discount_tax_0 = self.invoice.invoice_global_discount_ids.filtered(
            lambda x: x.tax_ids == self.tax_0
        )
        self.assertAlmostEqual(discount_tax_0.discount_amount, 20)

    def test_partner_defaults_apply_only_the_invoice_company_discount(self):
        other_data = self.setup_other_company()
        companies = self.env.company | other_data["company"]
        self.env.user.company_ids = companies
        self.env = self.env(
            context=dict(self.env.context, allowed_company_ids=companies.ids)
        )
        partner = self.env["res.partner"].create(
            {"name": "Shared discount customer", "company_id": False}
        )
        cases = []
        discounts = self.env["global.discount"]
        for data, rate, untaxed, total in (
            (self.company_data, 20, 160, 184),
            (other_data, 50, 100, 115),
        ):
            company = data["company"]
            account = data["default_account_revenue"]
            discount = (
                self.env["global.discount"]
                .with_company(company)
                .create(
                    {
                        "name": "Customer discount " + company.name,
                        "company_id": company.id,
                        "discount_scope": "sale",
                        "discount": rate,
                        "account_id": account.id,
                    }
                )
            )
            discounts |= discount
            cases.append((company, account, discount, untaxed, total))
        partner.customer_global_discount_ids = discounts
        self.assertEqual(partner.customer_global_discount_ids, discounts)
        for company, account, discount, untaxed, total in cases:
            with self.subTest(company=company.name):
                tax = (
                    self.env["account.tax"]
                    .with_company(company)
                    .create(
                        {
                            "name": "Company discount tax",
                            "company_id": company.id,
                            "type_tax_use": "sale",
                            "amount_type": "percent",
                            "amount": 15,
                        }
                    )
                )
                invoice = (
                    self.env["account.move"]
                    .with_company(company)
                    .create(
                        {
                            "move_type": "out_invoice",
                            "partner_id": partner.id,
                            "invoice_date": "2026-01-15",
                            "invoice_line_ids": [
                                Command.create(
                                    {
                                        "name": "Company service",
                                        "account_id": account.id,
                                        "quantity": 1,
                                        "price_unit": 200,
                                        "tax_ids": [Command.set(tax.ids)],
                                    }
                                )
                            ],
                        }
                    )
                )
                self.assertEqual(invoice.company_id, company)
                self.assertEqual(invoice.global_discount_ids, discount)
                applied = invoice.invoice_global_discount_ids
                self.assertEqual(applied.global_discount_id, discount)
                self.assertEqual(applied.account_id, account)
                self.assertEqual(applied.company_id, company)
                self.assertEqual(invoice.amount_untaxed, untaxed)
                self.assertEqual(invoice.amount_tax, total - untaxed)
                self.assertEqual(invoice.amount_total, total)
                invoice.action_post()
                self.assertEqual(invoice.state, "posted")
                self.assertAlmostEqual(sum(invoice.line_ids.mapped("balance")), 0)

    def test_customer_invoice_inherits_the_partner_discount(self):
        self.partner_1.customer_global_discount_ids = self.global_discount_1
        tax = self.tax_sale_a.copy(
            default={"amount": 15.0, "name": "Partner discount contract tax"}
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_1.id,
                "invoice_date": "2026-01-15",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Discounted service",
                            "quantity": 1,
                            "price_unit": 200.0,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        self.assertEqual(invoice.global_discount_ids, self.global_discount_1)
        self.assertEqual(len(invoice.invoice_global_discount_ids), 1)
        self.assertEqual(invoice.amount_global_discount, -40.0)
        self.assertEqual(invoice.amount_untaxed, 160.0)
        self.assertEqual(invoice.amount_tax, 24.0)
        self.assertEqual(invoice.amount_total, 184.0)
        self.assertEqual(invoice.currency_id, invoice.company_id.currency_id)
        invoice.action_post()

        rows = (
            self.env["account.invoice.report"]
            .with_context(allowed_company_ids=invoice.company_id.ids)
            .search_read(
                [
                    ("move_id", "=", invoice.id),
                    ("company_id", "=", invoice.company_id.id),
                    ("state", "=", "posted"),
                ],
                [
                    "company_id",
                    "company_currency_id",
                    "currency_id",
                    "price_subtotal",
                    "price_subtotal_currency",
                    "price_total",
                    "price_total_currency",
                ],
            )
        )
        service = invoice.invoice_line_ids.filtered(
            lambda line: not line.invoice_global_discount_id
        )
        discount = invoice.line_ids.filtered("invoice_global_discount_id")
        self.assertEqual(len(service), 1)
        self.assertEqual(len(discount), 1)
        self.assertEqual({row["id"] for row in rows}, {service.id, discount.id})
        expected = {service.id: (200.0, 230.0), discount.id: (-40.0, -46.0)}
        for row in rows:
            self.assertEqual(row["company_id"][0], invoice.company_id.id)
            for field in ("company_currency_id", "currency_id"):
                self.assertEqual(row[field][0], invoice.currency_id.id)
            subtotal, total = expected[row["id"]]
            for field in ("price_subtotal", "price_subtotal_currency"):
                self.assertAlmostEqual(row[field], subtotal)
            for field in ("price_total", "price_total_currency"):
                self.assertAlmostEqual(row[field], total)
        self.assertAlmostEqual(sum(row["price_subtotal"] for row in rows), 160.0)
        self.assertAlmostEqual(sum(row["price_total"] for row in rows), 184.0)

    def test_09_customer_invoice(self):
        global_discount = self.global_discount_obj.create(
            {
                "name": "Test Discount Sales",
                "discount_scope": "sale",
                "discount": 50,
                "account_id": self.account.id,
                "sequence": 1,
            }
        )
        tax = self.tax_sale_a.copy(default={"amount": 15.0, "name": "Tax 2"})
        invoice = (
            self.env["account.move"]
            .with_context(test_account_global_discount=True)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_1.id,
                    "global_discount_ids": [Command.set(global_discount.ids)],
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "Line 1",
                                "price_unit": 200.0,
                                "quantity": 1,
                                "tax_ids": [Command.set(tax.ids)],
                            },
                        )
                    ],
                }
            )
        )
        self.assertEqual(len(invoice.invoice_global_discount_ids), 1)
        invoice_tax_line = invoice.line_ids.filtered("tax_line_id")
        self.assertAlmostEqual(invoice_tax_line.tax_base_amount, -100.0)
        self.assertAlmostEqual(invoice_tax_line.balance, -15.0)
        self.assertAlmostEqual(invoice.amount_untaxed, 100.0)
        self.assertAlmostEqual(invoice.amount_total, 115.0)
        self.assertAlmostEqual(invoice.amount_global_discount, -100.0)
        # Check journal item validity
        lines = invoice.line_ids
        line_15 = lines.filtered(
            lambda x: x.invoice_global_discount_id and x.tax_ids == tax
        )
        self.assertAlmostEqual(line_15.debit, 100)

    def test_10_customer_invoice_currency(self):
        """Multi-currency"""
        eur = self.env.ref("base.EUR")
        usd = self.env.ref("base.USD")
        self.assertEqual(self.env.user.company_id.currency_id, usd)
        self.invoice.currency_id = self.env.ref("base.EUR")
        invoice = self.invoice
        self.assertAlmostEqual(invoice.amount_total, 430.0)
        self.assertAlmostEqual(invoice.amount_untaxed, 400.0)
        self.assertAlmostEqual(invoice.amount_global_discount, 0)
        base_line = invoice.line_ids.filtered(
            lambda line: (
                line.tax_ids
                and not line.invoice_global_discount_id
                and not line.product_id
            )
        )
        base_line_with_product = invoice.line_ids.filtered(
            lambda line: (
                line.tax_ids and not line.invoice_global_discount_id and line.product_id
            )
        )
        self.assertEqual(len(base_line) + len(base_line_with_product), 2)
        self.assertAlmostEqual(
            base_line.balance + base_line_with_product.balance,
            eur._convert(
                invoice.amount_untaxed, usd, self.env.user.company_id, invoice.date
            ),
        )
        tax_line = invoice.line_ids.filtered(
            lambda line: line.tax_line_id and not line.invoice_global_discount_id
        )
        line_with_tax = invoice.line_ids.filtered(
            lambda line: line.tax_ids.amount > 0 and not line.invoice_global_discount_id
        )
        self.assertEqual(len(tax_line), 1)
        tax_line_balance_before_discount = tax_line.balance
        self.assertAlmostEqual(
            tax_line_balance_before_discount,
            eur._convert(
                line_with_tax.balance * (self.tax.amount / 100),
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
        self.assertAlmostEqual(
            tax_line.tax_base_amount,
            eur._convert(
                line_with_tax.balance,
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
        discount_line = invoice.line_ids.filtered("invoice_global_discount_id")
        self.assertFalse(discount_line)
        with Form(self.invoice) as invoice_form:
            invoice_form.global_discount_ids.add(self.global_discount_1)
        invoice = invoice_form.save()
        # Check that when we add a global discount it will be based on the
        # correct currency
        self.assertAlmostEqual(invoice.amount_total, 384)
        self.assertAlmostEqual(invoice.amount_untaxed, 360.0)
        self.assertAlmostEqual(invoice.amount_global_discount, -40.0)
        base_line = invoice.line_ids.filtered(
            lambda line: (
                line.tax_ids
                and not line.invoice_global_discount_id
                and not line.product_id
            )
        )
        base_line_with_product = invoice.line_ids.filtered(
            lambda line: (
                line.tax_ids and not line.invoice_global_discount_id and line.product_id
            )
        )
        self.assertEqual(len(base_line) + len(base_line_with_product), 2)
        self.assertAlmostEqual(
            base_line.balance + base_line_with_product.balance,
            eur._convert(
                invoice.amount_untaxed_before_global_discounts,
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
        tax_line = invoice.line_ids.filtered(
            lambda line: line.tax_line_id and not line.invoice_global_discount_id
        )
        line_without_tax = invoice.line_ids.filtered(
            lambda line: line.tax_ids.amount == 0
            and not line.tax_line_id
            and line.product_id
            and not line.invoice_global_discount_id
        )
        self.assertEqual(len(tax_line), 1)
        self.assertAlmostEqual(
            tax_line.tax_base_amount + line_without_tax.balance,
            eur._convert(
                invoice.amount_untaxed,
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
        self.assertAlmostEqual(
            tax_line.balance,
            eur._convert(
                (invoice.amount_untaxed - line_without_tax.balance)
                * (self.tax.amount / 100),
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
        self.assertLess(tax_line.balance, tax_line_balance_before_discount)
        discount_line = invoice.line_ids.filtered("invoice_global_discount_id")
        self.assertEqual(len(discount_line), 1)
        self.assertAlmostEqual(
            discount_line.balance,
            eur._convert(
                invoice.amount_global_discount,
                usd,
                self.env.user.company_id,
                invoice.date,
            ),
        )
