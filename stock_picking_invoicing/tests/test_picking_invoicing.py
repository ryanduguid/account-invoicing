# Copyright (C) 2019-Today: Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import Command, exceptions
from odoo.tests import Form

from .common import TestPickingInvoicingCommon


class TestPickingInvoicing(TestPickingInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking_model = cls.env["stock.picking"]
        cls.move_model = cls.env["stock.move"]
        cls.invoice_model = cls.env["account.move"]
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Deco Addict",
                "is_company": True,
                "street": "77 Santa Barbara Rd",
                "city": "Pleasant Hill",
                "state_id": cls.env.ref("base.state_us_5").id,
                "zip": "94523",
                "country_id": cls.env.ref("base.us").id,
                "email": "deco_addict@yourcompany.example.com",
                "phone": "(603)-996-3829",
                "website": "http://www.deco-addict.com",
                "vat": "US12345673",
            }
        )
        cls.partner.write(
            {
                "property_payment_term_id": cls.env.ref(
                    "account.account_payment_term_immediate"
                ).id
            }
        )
        cls.partner2 = cls.env["res.partner"].create(
            {
                "name": "Floyd Steward",
                "parent_id": cls.partner.id,
                "function": "Analyst",
                "email": "floyd.steward34@example.com",
                "phone": "(145)-138-3401",
            }
        )
        cls.partner3 = cls.env["res.partner"].create(
            {
                "name": "Lumber Inc",
                "is_company": True,
                "street": "1337 N San Joaquin St",
                "city": "Stockton",
                "state_id": cls.env.ref("base.state_us_5").id,
                "zip": "95202",
                "email": "lumber-inv92@example.com",
                "phone": "(828)-316-0593",
                "country_id": cls.env.ref("base.us").id,
                "website": "http://www.lumber-inc.com",
                "vat": "US12345678",
            }
        )
        cls.partner4 = cls.env["res.partner"].create(
            {
                "name": "Ready Mat",
                "is_company": True,
                "street": "7500 W Linne Road",
                "city": "Tracy",
                "state_id": cls.env.ref("base.state_us_5").id,
                "zip": "95304",
                "email": "ready.mat28@example.com",
                "phone": "(803)-873-6126",
                "country_id": cls.env.ref("base.us").id,
                "website": "http://www.ready-mat.com/",
                "vat": "US12345675",
            }
        )
        cls.supplier = cls.env["res.partner"].create(
            {
                "name": "Azure Interior",
                "is_company": True,
                "street": "4557 De Silva St",
                "city": "Fremont",
                "state_id": cls.env.ref("base.state_us_5").id,
                "zip": "94538",
                "phone": "(870)-931-0505",
                "country_id": cls.env.ref("base.us").id,
                "email": "azure.Interior24@example.com",
                "website": "http://www.azure-interior.com",
                "vat": "US12345677",
            }
        )
        cls.pick_type_in = cls.env.ref("stock.picking_type_in")
        cls.pick_type_out = cls.env.ref("stock.picking_type_out")
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.customers_location = cls.env.ref("stock.stock_location_customers")
        cls.suppliers_location = cls.env.ref("stock.stock_location_suppliers")
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "A super journal name",
                "code": "ABC",
                "type": "sale",
                "refund_sequence": True,
            }
        )

        cls.product_model = cls.env["product.product"]
        cls.fiscal_position_model = cls.env["account.fiscal.position"]
        cls.fiscal_position_account_model = cls.env["account.fiscal.position.account"]
        cls.tax_model = cls.env["account.tax"]
        cls.account_receivable = cls.env["account.account"].search(
            [
                (
                    "account_type",
                    "=",
                    "asset_receivable",
                )
            ],
            limit=1,
        )
        cls.account_revenue = cls.env["account.account"].search(
            [("account_type", "=", "expense_direct_cost")], limit=1
        )

        cls.tax_sale_1 = cls.tax_model.create(
            {"name": "Sale tax 20", "type_tax_use": "sale", "amount": "20.00"}
        )
        cls.tax_sale_2 = cls.tax_model.create(
            {"name": "Sale tax 10", "type_tax_use": "sale", "amount": "10.00"}
        )
        cls.tax_purchase_1 = cls.tax_model.create(
            {"name": "Purchase tax 10", "type_tax_use": "purchase", "amount": "10.00"}
        )
        cls.tax_purchase_2 = cls.tax_model.create(
            {"name": "Purchase tax 20", "type_tax_use": "purchase", "amount": "20.00"}
        )

        cls.product_test_1 = cls.product_model.create(
            {
                "name": "Test 1",
                "lst_price": "15000",
                "taxes_id": [(6, 0, [cls.tax_sale_1.id, cls.tax_sale_2.id])],
                "supplier_taxes_id": [
                    (6, 0, [cls.tax_purchase_1.id, cls.tax_purchase_2.id])
                ],
                "property_account_income_id": cls.account_revenue.id,
                "standard_price": "500",
            }
        )
        cls.product_test_2 = cls.product_model.create(
            {
                "name": "Test 2",
                "lst_price": "15000",
                "taxes_id": [(6, 0, [cls.tax_sale_1.id, cls.tax_sale_2.id])],
                "supplier_taxes_id": [
                    (6, 0, [cls.tax_purchase_1.id, cls.tax_purchase_2.id])
                ],
                "property_account_income_id": cls.account_revenue.id,
                "standard_price": "500",
            }
        )
        cls.picking_in = cls.picking_model.create(
            {
                "partner_id": cls.partner.id,
                "picking_type_id": cls.pick_type_in.id,
                "invoice_state": "2binvoiced",
                "location_id": cls.suppliers_location.id,
                "location_dest_id": cls.stock_location.id,
            }
        )

        # Test PriceList and Sellers Price
        cls.product_category_office = cls.env["product.category"].create(
            {
                "name": "Office Furniture",
            }
        )
        cls.product_price_test = cls.product_model.create(
            {
                "name": "Large Cabinet",
                "categ_id": cls.env["product.category"]
                .create(
                    {
                        "name": "Office Furniture",
                    }
                )
                .id,
                "standard_price": 800.0,
                "list_price": 320.0,
                "type": "consu",
                "weight": 0.330,
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "default_code": "E-COM07",
            }
        )
        cls.price_list = cls.env["product.pricelist"].create({"name": "Test pricelist"})
        cls.price_list.item_ids.create(
            {
                "compute_price": "fixed",
                "fixed_price": 1234.0,
                "applied_on": "0_product_variant",
                "product_id": cls.product_price_test.id,
            }
        )
        # Data has duplicate line with 2 Prices for same Partner,
        # just remove one for the test.
        # seller_to_delete = cls.product_price_test.seller_ids.filtered(
        #     lambda line: line.price == 785.0
        #     and line.partner_id == cls.env.ref("base.res_partner_4")
        # )
        # seller_to_delete.unlink()

    def test_empty_draft_picking_defaults_to_sales_without_creating_an_invoice(self):
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        before = (picking.state, picking.invoice_state)
        before_count = self.invoice_model.search_count([])
        wizard_form = Form(
            self.env["stock.invoice.onshipping"].with_context(
                active_model=picking._name,
                active_id=picking.id,
                active_ids=picking.ids,
                lang="en_US",
            )
        )
        self.assertEqual(wizard_form.journal_type, "sale")
        wizard = wizard_form.save()
        with self.assertRaisesRegex(exceptions.UserError, "No invoice created!"):
            wizard.action_generate()
        self.assertEqual(self.invoice_model.search_count([]), before_count)
        self.assertEqual((picking.state, picking.invoice_state), before)
        self.assertEqual(picking.state, "draft")
        self.assertFalse(picking.move_ids)
        self.assertFalse(picking.invoice_ids)

    def test_invoice_generation_refuses_a_picking_from_another_current_company(self):
        current_company = self.env.company
        other_company = self.env["res.company"].create(
            {"name": "Fabricated stock invoice company"}
        )
        companies = [current_company.id, other_company.id]
        warehouses = self.env["stock.warehouse"].with_context(
            allowed_company_ids=companies
        )
        warehouse = warehouses.create(
            {
                "name": "Fabricated stock invoice warehouse",
                "code": "FSIW",
                "company_id": other_company.id,
            }
        )
        picking = (
            self.picking_model.with_context(allowed_company_ids=companies)
            .with_company(other_company)
            .create(
                {
                    "partner_id": self.partner.id,
                    "picking_type_id": warehouse.out_type_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": self.customers_location.id,
                }
            )
        )
        self.move_model.with_env(picking.env).create(
            {
                "product_id": self.product_test_1.id,
                "picking_id": picking.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "product_uom_qty": 1,
                "product_uom": self.product_test_1.uom_id.id,
            }
        )
        self.picking_move_state(picking)
        picking.set_to_be_invoiced()
        self.assertEqual(picking.company_id, other_company)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.invoice_state, "2binvoiced")
        before_move_states = picking.move_ids.mapped("invoice_state")
        invoices = self.invoice_model.with_context(allowed_company_ids=companies)
        before_count = invoices.search_count([])
        wizard = (
            self.env["stock.invoice.onshipping"]
            .with_context(
                allowed_company_ids=companies,
                active_model=picking._name,
                active_id=picking.id,
                active_ids=picking.ids,
                lang="en_US",
            )
            .create({})
        )
        self.assertEqual(wizard.env.company, current_company)
        with self.assertRaisesRegex(
            exceptions.UserError, "All pickings are not related to your company!"
        ):
            wizard.action_generate()
        self.assertEqual(invoices.search_count([]), before_count)
        self.assertFalse(picking.invoice_ids)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.invoice_state, "2binvoiced")
        self.assertEqual(picking.move_ids.mapped("invoice_state"), before_move_states)

    def test_nonbillable_first_picking_does_not_change_customer_invoice(self):
        before_count = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice", "property_product_pricelist": False})
        product = self.product_model.create(
            {
                "name": "Eligible delivery sample",
                "type": "consu",
                "list_price": 25.0,
                "standard_price": 7.0,
                "taxes_id": [Command.clear()],
                "supplier_taxes_id": [Command.clear()],
                "property_account_income_id": self.account_revenue.id,
                "property_account_expense_id": self.account_revenue.id,
            }
        )
        pickings = self.picking_model.browse()
        for incoming in (True, False):
            picking = self.picking_model.create(
                {
                    "partner_id": self.supplier.id if incoming else self.partner.id,
                    "picking_type_id": (
                        self.pick_type_in.id if incoming else self.pick_type_out.id
                    ),
                    "location_id": (
                        self.suppliers_location.id
                        if incoming
                        else self.stock_location.id
                    ),
                    "location_dest_id": (
                        self.stock_location.id
                        if incoming
                        else self.customers_location.id
                    ),
                }
            )
            self.move_model.create(
                {
                    "product_id": product.id,
                    "picking_id": picking.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "product_uom_qty": 2,
                    "product_uom": product.uom_id.id,
                }
            )
            if not incoming:
                picking.set_to_be_invoiced()
            self.picking_move_state(picking)
            self.assertEqual(picking.state, "done")
            pickings |= picking
        excluded, delivery = pickings
        self.assertEqual(excluded.invoice_state, "none")
        self.assertEqual(delivery.invoice_state, "2binvoiced")
        wizard_form = Form(
            self.env["stock.invoice.onshipping"].with_context(
                active_ids=pickings.ids, active_model=pickings._name
            )
        )
        self.assertEqual(wizard_form.group, "picking")
        action = wizard_form.save().action_generate()
        invoice = self.invoice_model.search([("picking_ids", "in", pickings.ids)])
        self.assertEqual(len(invoice), 1)
        self.assertEqual(self.invoice_model.search_count([]), before_count + 1)
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.journal_id.type, "sale")
        self.assertEqual(
            action["id"], self.env.ref("account.action_move_out_invoice_type").id
        )
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(invoice.picking_ids, delivery)
        self.assertFalse(excluded.invoice_ids)
        self.assertEqual(excluded.invoice_state, "none")
        self.assertEqual(excluded.move_ids.mapped("invoice_state"), ["none"])
        self.assertEqual(delivery.invoice_state, "invoiced")
        line = invoice.invoice_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, product)
        self.assertEqual(line.move_line_ids, delivery.move_ids)
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.price_unit, 25.0)
        self.assertFalse(line.tax_ids)
        self.assertEqual(invoice.amount_untaxed, 50.0)
        self.assertEqual(invoice.amount_total, 50.0)

    def test_vendor_bill_uses_the_supplier_quantity_break(self):
        product = self.product_model.create(
            {
                "name": "Quantity-priced cabinet",
                "type": "consu",
                "standard_price": 800.0,
                "uom_id": self.env.ref("uom.product_uom_unit").id,
                "taxes_id": [Command.clear()],
                "supplier_taxes_id": [Command.clear()],
            }
        )
        for quantity, price in ((0, 120.0), (10, 100.0)):
            self.env["product.supplierinfo"].create(
                {
                    "partner_id": self.supplier.id,
                    "product_tmpl_id": product.product_tmpl_id.id,
                    "min_qty": quantity,
                    "price": price,
                    "currency_id": self.env.company.currency_id.id,
                }
            )
        for quantity, price in ((1, 120.0), (10, 100.0)):
            with self.subTest(quantity=quantity):
                picking = self.picking_model.create(
                    {
                        "partner_id": self.supplier.id,
                        "picking_type_id": self.pick_type_in.id,
                        "invoice_state": "2binvoiced",
                        "location_id": self.suppliers_location.id,
                        "location_dest_id": self.stock_location.id,
                    }
                )
                self.move_model.create(
                    {
                        "product_id": product.id,
                        "picking_id": picking.id,
                        "location_id": self.suppliers_location.id,
                        "location_dest_id": self.stock_location.id,
                        "product_uom_qty": quantity,
                        "product_uom": product.uom_id.id,
                    }
                )
                self.picking_move_state(picking)
                self.assertEqual(picking.state, "done")
                wizard = Form(
                    self.env["stock.invoice.onshipping"].with_context(
                        active_ids=picking.ids, active_model=picking._name
                    )
                ).save()
                action = wizard.action_generate()
                invoice = self.invoice_model.search(
                    [("picking_ids", "in", picking.ids)]
                )
                self.assertEqual(
                    action["id"], self.env.ref("account.action_move_in_invoice_type").id
                )
                self.assertEqual(len(invoice), 1)
                self.assertEqual(invoice.move_type, "in_invoice")
                self.assertEqual(invoice.partner_id, self.supplier)
                self.assertEqual(invoice.picking_ids, picking)
                self.assertEqual(len(invoice.invoice_line_ids), 1)
                self.assertEqual(invoice.invoice_line_ids.product_id, product)
                self.assertEqual(invoice.invoice_line_ids.quantity, quantity)
                self.assertEqual(invoice.invoice_line_ids.price_unit, price)
                self.assertEqual(invoice.amount_untaxed, quantity * price)
                self.assertEqual(invoice.amount_total, quantity * price)
                invoice.action_post()
                self.assertEqual(invoice.state, "posted")

    def test_default_group_preserves_each_delivery_and_zero_prices(self):
        self.partner.write({"type": "invoice", "property_product_pricelist": False})
        for price in (0.0, 25.0):
            with self.subTest(price=price):
                product = self.product_model.create(
                    {
                        "name": "Separate delivery sample",
                        "type": "consu",
                        "list_price": price,
                        "taxes_id": [Command.clear()],
                        "supplier_taxes_id": [Command.clear()],
                        "property_account_income_id": self.account_revenue.id,
                    }
                )
                pickings = self.picking_model.browse()
                for quantity in (2, 3):
                    picking = self.picking_model.create(
                        {
                            "partner_id": self.partner.id,
                            "picking_type_id": self.pick_type_out.id,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customers_location.id,
                        }
                    )
                    self.move_model.create(
                        {
                            "product_id": product.id,
                            "picking_id": picking.id,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customers_location.id,
                            "product_uom_qty": quantity,
                            "product_uom": product.uom_id.id,
                        }
                    )
                    picking.set_to_be_invoiced()
                    self.picking_move_state(picking)
                    self.assertEqual(picking.state, "done")
                    pickings |= picking
                wizard_form = Form(
                    self.env["stock.invoice.onshipping"].with_context(
                        active_ids=pickings.ids, active_model=pickings._name
                    )
                )
                self.assertEqual(wizard_form.group, "picking")
                action = wizard_form.save().action_generate()
                invoices = self.invoice_model.search(
                    [("picking_ids", "in", pickings.ids)]
                )
                self.assertEqual(len(invoices), 2)
                self.assertEqual(self.invoice_model.search(action["domain"]), invoices)
                for picking, quantity in zip(pickings, (2, 3), strict=True):
                    invoice = invoices.filtered(
                        lambda invoice, picking=picking: invoice.picking_ids == picking
                    )
                    self.assertEqual(len(invoice), 1)
                    self.assertEqual(invoice.move_type, "out_invoice")
                    self.assertEqual(invoice.partner_id, self.partner)
                    self.assertEqual(invoice.company_id, picking.company_id)
                    self.assertEqual(picking.invoice_ids, invoice)
                    self.assertEqual(picking.invoice_state, "invoiced")
                    line = invoice.invoice_line_ids
                    self.assertEqual(len(line), 1)
                    self.assertEqual(line.product_id, product)
                    self.assertEqual(line.move_line_ids, picking.move_ids)
                    self.assertEqual(line.quantity, quantity)
                    self.assertEqual(line.price_unit, price)
                    self.assertFalse(line.tax_ids)
                    self.assertEqual(invoice.amount_untaxed, quantity * price)
                    self.assertEqual(invoice.amount_total, quantity * price)
                    invoice.action_post()
                    self.assertEqual(invoice.state, "posted")

    def test_0_picking_out_invoicing(self):
        # setting Agrolait type to default, because it's 'contact' in demo data
        nb_invoice_before = self.invoice_model.search_count([])
        # Test case to Get Price Unit to Invoice when Partner don't has Pricelist
        self.partner.write({"type": "invoice", "property_product_pricelist": False})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        new_move = self.move_model.create(move_vals)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))
        assert invoice.invoice_user_id, "Error to map User in Invoice."
        assert invoice.invoice_payment_term_id, "Error to map Payment Term in Invoice."
        assert invoice.fiscal_position_id, "Error to map Fiscal Position in Invoice."
        assert invoice.company_id, "Error to map Company in Invoice."
        assert invoice.invoice_line_ids, "Error to create invoice line."
        for inv_line in invoice.invoice_line_ids:
            assert inv_line.account_id, "Error to map Account in Invoice Line."
            assert inv_line.tax_ids, "Error to map Sale Tax in Invoice Line."
            assert inv_line.product_uom_id, "Error to map Product UOM in Invoice Line."
            assert inv_line.price_unit, "Error in Price Unit"
            assert inv_line.move_line_ids, (
                "Error, there no relation between Invoice Line and Stock Move Line."
            )
            for mv_line in inv_line.move_line_ids:
                self.assertEqual(
                    mv_line.id,
                    new_move.id,
                    "Error to link stock.move with invoice.line.",
                )

    def test_1_picking_out_invoicing(self):
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")

        # Test Wizard Error
        # self.create_invoice_wizard(picking)
        wizard_obj = self.env["stock.invoice.onshipping"].with_context(
            active_ids=picking.ids,
            active_model=picking._name,
            active_id=picking.id,
        )
        fields_list = wizard_obj.fields_get().keys()
        wizard_values = wizard_obj.default_get(fields_list)
        wizard = wizard_obj.create(wizard_values)
        wizard.onchange_group()
        with self.assertRaises(exceptions.UserError) as e:
            wizard.with_context(lang="en_US").action_generate()
        msg = "No invoice created!"
        self.assertIn(msg, e.exception.args[0])
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after)

    def test_2_picking_out_invoicing(self):
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        new_move = self.move_model.create(move_vals)
        picking.set_to_be_invoiced()

        # Test Set Not Invoice
        picking.set_as_not_billable()
        self.assertEqual(picking.invoice_state, "none")
        # Test Set Invoiced
        picking.set_as_invoiced()
        self.assertEqual(picking.invoice_state, "invoiced")

        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))
        assert invoice.invoice_line_ids, "Error to create invoice line."
        for inv_line in invoice.invoice_line_ids:
            for mv_line in inv_line.move_line_ids:
                self.assertEqual(
                    mv_line.id,
                    new_move.id,
                    "Error to link stock.move with invoice.line.",
                )
            self.assertTrue(inv_line.tax_ids, "Error to map Sale Tax in invoice.line.")

    def test_3_picking_out_invoicing(self):
        """
        Test invoicing picking in to check if get the taxes
        from supplier_taxes_id.
        """
        nb_invoice_before = self.invoice_model.search_count([])
        picking = self.picking_model.create(
            {
                "partner_id": self.supplier.id,
                "picking_type_id": self.pick_type_in.id,
                "location_id": self.suppliers_location.id,
                "location_dest_id": self.stock_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.stock_location.id,
            "location_id": self.suppliers_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        new_move = self.move_model.create(move_vals)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.supplier)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))
        assert invoice.invoice_line_ids, "Error to create invoice line."
        for inv_line in invoice.invoice_line_ids:
            for mv_line in inv_line.move_line_ids:
                self.assertEqual(
                    mv_line.id,
                    new_move.id,
                    "Error to link stock.move with invoice.line.",
                )
            self.assertTrue(
                inv_line.tax_ids,
                "Error to map Purchase Tax in invoice.line.",
            )

    def test_4_picking_out_invoicing_backorder(self):
        """
        Test invoicing picking out to check if backorder is create
        with same invoice state.
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 4,
            "product_uom": self.product_test_1.uom_id.id,
        }
        new_move = self.move_model.create(move_vals)
        picking.set_to_be_invoiced()
        # Test BackOrder need to open Wizard
        # self.picking_move_state(picking)
        picking.action_confirm()
        # Check product availability
        picking.action_assign()
        # Force product availability
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty / 2.0
            # Test Price Unit informed by User
            move.price_unit = 345.0

        backorder = self.create_backorder_wizard(picking)
        backorder.action_assign()
        self.assertEqual(backorder.invoice_state, "2binvoiced")

        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))
        assert invoice.invoice_line_ids, "Error to create invoice line."
        for inv_line in invoice.invoice_line_ids:
            for mv_line in inv_line.move_line_ids:
                self.assertEqual(
                    mv_line.id,
                    new_move.id,
                    "Error to link stock.move with invoice.line.",
                )
            self.assertTrue(inv_line.tax_ids, "Error to map Sale Tax in invoice.line.")
            # Test Price Unit informed by user
            self.assertEqual(
                inv_line.price_unit, 345.0, "Error in Price Unit informed by User."
            )

    def test_picking_cancel(self):
        """
        Ensure that the invoice_state of the picking is correctly
        updated when an invoice is cancelled
        :return:
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        invoice.button_cancel()
        self.assertEqual(picking.invoice_state, "2binvoiced")
        invoice.button_draft()
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))

    def test_picking_invoice_refund(self):
        """
        Ensure that a refund keep the link to the picking
        :return:
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner2.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 2,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        invoice.action_post()
        refund = invoice._reverse_moves(cancel=True)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertIn(picking, refund.picking_ids)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice | refund))

    def test_picking_invoicing_by_product1(self):
        """
        Test the invoice generation grouped by partner/product with 1
        picking and 2 moves.
        :return:
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        move_vals2 = {
            "product_id": self.product_test_2.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_2.uom_id.id,
        }
        self.move_model.create(move_vals2)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        products = invoice.invoice_line_ids.mapped("product_id")
        self.assertEqual(len(invoice.invoice_line_ids), 2)
        self.assertIn(self.product_test_1, products)
        self.assertIn(self.product_test_2, products)
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoice))

    def test_picking_invoicing_by_product2(self):
        """
        Test the invoice generation grouped by partner/product with 2
        picking and 2 moves per picking.
        We use same partner for 2 picking so we should have 1 invoice with 2
        lines (and qty 2)
        :return:
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        picking2 = picking.copy()
        move_vals2 = {
            "product_id": self.product_test_1.id,
            "picking_id": picking2.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals2)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)
        picking2.set_to_be_invoiced()
        self.picking_move_state(picking2)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking2.state, "done")
        pickings = picking | picking2
        invoice = self.create_invoice_wizard(pickings)
        self.assertEqual(len(invoice), 1)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(picking2.invoice_state, "invoiced")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn(invoice, picking.invoice_ids)
        self.assertIn(invoice, picking2.invoice_ids)
        self.assertIn(picking, invoice.picking_ids)
        self.assertIn(picking2, invoice.picking_ids)
        products = invoice.invoice_line_ids.mapped("product_id")
        self.assertIn(self.product_test_1, products)
        for inv_line in invoice.invoice_line_ids:
            # qty = 3 because 1 move + duplicate one + 1 new
            self.assertAlmostEqual(inv_line.quantity, 3)
            self.assertTrue(inv_line.tax_ids, "Error to map Sale Tax in invoice.line.")
        # Now test behaviour if the invoice is delete
        invoice.unlink()
        for picking in pickings:
            self.assertEqual(picking.invoice_state, "2binvoiced")
        nb_invoice_after = self.invoice_model.search_count([])
        # Should be equals because we delete the invoice
        self.assertEqual(nb_invoice_before, nb_invoice_after)

    def test_picking_invoicing_by_product3(self):
        """
        Test the invoice generation grouped by partner/product with 2
        picking and 2 moves per picking.
        We use different partner for 2 picking so we should have 2 invoice
        with 2 lines (and qty 1)
        :return:
        """
        nb_invoice_before = self.invoice_model.search_count([])
        self.partner.write({"type": "invoice"})
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        move_vals = {
            "product_id": self.product_test_1.id,
            "picking_id": picking.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_1.uom_id.id,
        }
        self.move_model.create(move_vals)
        picking2 = picking.copy({"partner_id": self.partner3.id})
        move_vals2 = {
            "product_id": self.product_test_2.id,
            "picking_id": picking2.id,
            "location_dest_id": self.customers_location.id,
            "location_id": self.stock_location.id,
            "product_uom_qty": 1,
            "product_uom": self.product_test_2.uom_id.id,
        }
        self.move_model.create(move_vals2)
        picking.set_to_be_invoiced()
        self.picking_move_state(picking)

        picking2.set_to_be_invoiced()
        self.picking_move_state(picking2)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking2.state, "done")
        pickings = picking | picking2
        invoices = self.create_invoice_wizard(pickings)

        self.assertEqual(len(invoices), 2)
        self.assertEqual(picking.invoice_state, "invoiced")
        self.assertEqual(picking2.invoice_state, "invoiced")
        self.assertIn(self.partner, invoices.mapped("partner_id"))
        self.assertIn(self.partner3, invoices.mapped("partner_id"))
        for invoice in invoices:
            self.assertEqual(len(invoice.picking_ids), 1)
            picking = invoice.picking_ids
            self.assertIn(invoice, picking.invoice_ids)
            for inv_line in invoice.invoice_line_ids:
                self.assertAlmostEqual(inv_line.quantity, 1)
                self.assertTrue(
                    inv_line.tax_ids,
                    "Error to map Sale Tax in invoice.line.",
                )
            # Test the behaviour when the invoice is cancelled
            # The picking invoice_status should be updated
            invoice.button_cancel()
            self.assertEqual(picking.invoice_state, "2binvoiced")
        nb_invoice_after = self.invoice_model.search_count([])
        self.assertEqual(nb_invoice_before, nb_invoice_after - len(invoices))

    def test_0_counting_2binvoiced(self):
        """
        Check method counting 2binvoice used in kanban view
        """
        self.assertEqual(1, self.pick_type_in.count_picking_2binvoiced)

    def test_return_customer_picking(self):
        """
        Test Return Customer Picking and Invoice created.
        """
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "invoice_state": "2binvoiced",
                "origin": "stock_picking_invoicing demo",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        self.move_model.create(
            {
                "product_id": self.product_price_test.id,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
                "product_uom_qty": 1,
                "product_uom": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        # Confirm Invoice
        invoice.action_post()
        self.assertEqual(invoice.state, "posted", "Invoice should be in state Posted")
        # Check Invoice Type
        self.assertEqual(
            invoice.move_type, "out_invoice", "Invoice Type should be Out Invoice"
        )

        # Return Picking
        picking_devolution = self.return_picking_wizard(picking)

        self.assertEqual(picking_devolution.invoice_state, "2binvoiced")
        for line in picking_devolution.move_ids:
            self.assertEqual(line.invoice_state, "2binvoiced")

        self.picking_move_state(picking_devolution)
        self.assertEqual(picking_devolution.state, "done", "Change state fail.")
        invoice_devolution = self.create_invoice_wizard(picking_devolution)
        # Confirm Return Invoice
        invoice_devolution.action_post()
        self.assertEqual(
            invoice_devolution.state, "posted", "Invoice should be in state Posted"
        )
        # Check Invoice Type
        self.assertEqual(
            invoice_devolution.move_type,
            "out_refund",
            "Invoice Type should be Out Refund",
        )

    def test_return_supplier_picking(self):
        """
        Test Return Supplier Picking and Invoice created.
        """
        self.product_price_test.supplier_taxes_id = [Command.clear()]
        seller = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.partner4.id,
                "product_tmpl_id": self.product_price_test.product_tmpl_id.id,
                "min_qty": 0,
                "price": 125.0,
                "currency_id": self.env.company.currency_id.id,
            }
        )
        self.assertEqual(self.product_price_test.seller_ids, seller)
        picking = self.picking_model.create(
            {
                "partner_id": self.partner4.id,
                "picking_type_id": self.pick_type_in.id,
                "invoice_state": "2binvoiced",
                "origin": "stock_picking_invoicing demo",
                "location_id": self.suppliers_location.id,
                "location_dest_id": self.stock_location.id,
            }
        )
        self.move_model.create(
            {
                "product_id": self.product_price_test.id,
                "picking_id": picking.id,
                "location_id": self.suppliers_location.id,
                "location_dest_id": self.stock_location.id,
                "product_uom_qty": 1,
                "product_uom": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        # Confirm Invoice
        invoice.action_post()
        self.assertEqual(invoice.state, "posted", "Invoice should be in state Posted")
        # Check Invoice Type
        self.assertEqual(
            invoice.move_type, "in_invoice", "Invoice Type should be In Invoice"
        )

        # Return Picking
        picking_devolution = self.return_picking_wizard(picking)

        self.assertEqual(picking_devolution.invoice_state, "2binvoiced")
        for line in picking_devolution.move_ids:
            self.assertEqual(line.invoice_state, "2binvoiced")

        self.picking_move_state(picking_devolution)
        self.assertEqual(picking_devolution.state, "done", "Change state fail.")

        invoice_devolution = self.create_invoice_wizard(picking_devolution)
        for document, move_type, source in (
            (invoice, "in_invoice", picking),
            (invoice_devolution, "in_refund", picking_devolution),
        ):
            with self.subTest(move_type=move_type):
                self.assertEqual(len(document), 1)
                self.assertEqual(document.move_type, move_type)
                self.assertEqual(document.partner_id, self.partner4)
                self.assertEqual(document.currency_id, self.env.company.currency_id)
                self.assertEqual(document.picking_ids, source)
                self.assertEqual(len(document.invoice_line_ids), 1)
                self.assertEqual(
                    document.invoice_line_ids.product_id, self.product_price_test
                )
                self.assertEqual(document.invoice_line_ids.quantity, 1)
                self.assertEqual(document.invoice_line_ids.price_unit, 125.0)
                self.assertEqual(document.amount_untaxed, 125.0)
                self.assertEqual(document.amount_tax, 0.0)
                self.assertEqual(document.amount_total, 125.0)
        # Confirm Return Invoice
        invoice_devolution.action_post()
        self.assertEqual(
            invoice_devolution.state, "posted", "Invoice should be in state Posted"
        )
        # Check Invoice Type
        self.assertEqual(
            invoice_devolution.move_type,
            "in_refund",
            "Invoice Type should be In Refund",
        )

    def test_get_price_from_pricelist(self):
        """Test get Price from PriceList."""
        self.partner.write(
            {"type": "invoice", "property_product_pricelist": self.price_list.id}
        )
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "invoice_state": "2binvoiced",
                "origin": "stock_picking_invoicing demo",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        self.move_model.create(
            {
                "product_id": self.product_price_test.id,
                "product_uom_qty": 1,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
                "product_uom": self.product_price_test.uom_id.id,
            }
        )
        self.picking_move_state(picking)
        self.assertEqual(picking.state, "done")
        invoice = self.create_invoice_wizard(picking)
        self.assertEqual(picking.invoice_state, "invoiced")
        for inv_line in invoice.invoice_line_ids:
            if inv_line.product_id == self.product_price_test:
                self.assertEqual(
                    inv_line.price_unit,
                    1234.0,
                    "Error to get sale Price from Price List.",
                )

    def test_picking_extra_vals(self):
        """Test Picking Extra Vals"""
        picking = self.picking_model.create(
            {
                "partner_id": self.partner.id,
                "picking_type_id": self.pick_type_out.id,
                "invoice_state": "2binvoiced",
                "origin": "stock_picking_invoicing demo",
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
            }
        )
        self.move_model.create(
            {
                "product_id": self.product_test_1.id,
                "product_uom_qty": 1,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customers_location.id,
                "product_uom": self.product_test_1.uom_id.id,
            }
        )

        self._run_picking_onchanges(picking)

        for line in picking.move_ids:
            # Force Split
            line.quantity = 10

        picking.button_validate()
