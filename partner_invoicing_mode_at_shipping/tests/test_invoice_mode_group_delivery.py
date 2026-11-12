# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError

from odoo.addons.queue_job.tests.common import trap_jobs

from .common import InvoiceModeAtShippingCommon


class TestInvoiceModeAtShippingGrouped(InvoiceModeAtShippingCommon):
    def test_invoice_created_at_shipping_per_delivery(self):
        """Check that an invoice is created when goods are shipped."""
        self.partner.invoicing_mode = "standard"
        self.partner.one_invoice_per_shipping = True
        self._create_order()
        self.so1.action_confirm()
        picking = self.so1.picking_ids

        # Deliver partially
        picking.move_ids.write({"quantity": 2.0, "picked": True})
        with trap_jobs() as trap:
            picking._action_done()
            trap.assert_enqueued_job(
                picking._invoicing_at_shipping,
            )
            trap.perform_enqueued_jobs()

        self.assertEqual(picking.state, "done")
        invoice = self.so1.invoice_ids
        # Invoice is generated but is still draft
        self.assertEqual(
            "draft",
            invoice.state,
        )

        backorder = self.so1.picking_ids - picking
        self.assertTrue(backorder)

        backorder.move_ids.write({"quantity": 2.0, "picked": True})
        with trap_jobs() as trap:
            backorder._action_done()
            trap.assert_enqueued_job(
                backorder._invoicing_at_shipping,
            )
            with trap_jobs() as trap_invoice:
                trap.perform_enqueued_jobs()
                self.assertFalse(trap_invoice.enqueued_jobs)
        invoice_2 = self.so1.invoice_ids - invoice
        self.assertEqual(
            "draft",
            invoice_2.state,
        )
        # Launch the invoicing
        with trap_jobs() as trap:
            self.env["sale.order"].cron_generate_standard_invoices()
            trap.assert_enqueued_job(
                self.env["sale.order"]._validate_per_shipping_generated_invoices,
                args=(),
                kwargs={"companies": self.companies, "invoicing_mode": "standard"},
            )
            with trap_jobs() as trap_invoice:
                trap.perform_enqueued_jobs()
                trap_invoice.assert_enqueued_job(
                    self.so1.invoice_ids[0]._validate_invoice
                )
                trap_invoice.assert_enqueued_job(
                    self.so1.invoice_ids[1]._validate_invoice
                )
                trap_invoice.perform_enqueued_jobs()
        self.assertEqual("posted", invoice.state)
        self.assertEqual("posted", invoice_2.state)

    def test_shipping_invoice_batch_defaults_to_current_company(self):
        partner = self._create_partner(
            "Shipping batch fixture",
            invoicing_mode="standard",
            one_invoice_per_shipping=True,
        )
        order = self._create_sale_orders(
            1,
            partner_id=partner.id,
            partner_invoice_id=partner.id,
            partner_shipping_id=partner.id,
        )
        order.action_confirm()
        picking = order.picking_ids
        picking.move_ids.write({"quantity": 4, "picked": True})
        with trap_jobs() as shipping_jobs:
            picking._action_done()
            shipping_jobs.assert_jobs_count(1)
            shipping_jobs.assert_enqueued_job(picking._invoicing_at_shipping)
            shipping_jobs.perform_enqueued_jobs()
        self.assertEqual(picking.state, "done")
        invoice = order.invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.company_id, self.env.company)
        self.assertAlmostEqual(invoice.amount_total, 492)

        with trap_jobs() as batch_jobs:
            self.env["sale.order"].generate_invoices()
            batch_jobs.assert_jobs_count(1)
            with trap_jobs() as validation_jobs:
                batch_jobs.perform_enqueued_jobs()
                validation_jobs.assert_jobs_count(1)
                validation_jobs.assert_enqueued_job(invoice._validate_invoice)
                validation_jobs.perform_enqueued_jobs()
        self.assertEqual(order.invoice_ids, invoice)
        self.assertEqual(invoice.state, "posted")
        self.assertAlmostEqual(invoice.amount_total, 492)

    def test_shipping_delay_rejects_negative_days(self):
        self.assertEqual(self.partner.invoicing_at_shipping_delay, 0)
        with (
            self.assertRaisesRegex(
                ValidationError, "The invoicing at shipping delay cannot be negative"
            ),
            self.env.cr.savepoint(),
        ):
            self.partner.invoicing_at_shipping_delay = -1
        self.assertEqual(self.partner.invoicing_at_shipping_delay, 0)
        self.partner.invoicing_at_shipping_delay = 1
        self.assertEqual(self.partner.invoicing_at_shipping_delay, 1)

    def test_invoice_created_at_shipping_per_delivery_constrains(self):
        with self.assertRaises(ValidationError):
            self.partner.write(
                {"one_invoice_per_shipping": True, "invoicing_mode": "at_shipping"}
            )
        with self.assertRaises(ValidationError):
            self.partner.write(
                {"one_invoice_per_order": True, "one_invoice_per_shipping": True}
            )
