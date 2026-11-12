# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_receipt_journal import rename_old_italian_data


@tagged("post_install", "-at_install")
class TestReceiptMigration(AccountTestInvoicingCommon):
    JOURNAL_FIELDS = [
        "name",
        "code",
        "type",
        "receipts",
        "sequence",
        "company_id",
        "currency_id",
    ]

    def setUp(self):
        super().setUp()
        self.assertFalse(
            self.env["ir.module.module"].search(
                [("name", "=", "l10n_it_corrispettivi")]
            )
        )
        self.assertFalse(
            self.env["ir.model.data"].search(
                [
                    ("module", "=", "account_receipt_journal"),
                    ("name", "=", "sale_receipts_journal"),
                ]
            )
        )
        self.journal = self.env["account.journal"].create(
            {
                "name": "Preserved legacy receipts journal",
                "code": "LREC",
                "type": "sale",
                "receipts": True,
                "sequence": 99,
            }
        )
        self.xmlid = self.env["ir.model.data"].create(
            {
                "module": "l10n_it_corrispettivi",
                "name": "corrispettivi_journal",
                "model": "account.journal",
                "res_id": self.journal.id,
                "noupdate": True,
            }
        )
        self.xmlid.flush_recordset(["module", "name", "model", "res_id"])
        self.journal_before = self.journal.read(self.JOURNAL_FIELDS)
        self.journal_count = self.env["account.journal"].search_count([])

    def _assert_journal_preserved(self):
        # Refresh SQL migration results before testing data preservation.
        self.journal.invalidate_recordset(self.JOURNAL_FIELDS)
        self.xmlid.invalidate_recordset(
            ["module", "name", "model", "res_id", "noupdate"]
        )
        self.env.registry.clear_cache()
        self.assertEqual(self.journal.read(self.JOURNAL_FIELDS), self.journal_before)
        self.assertEqual(
            self.env["account.journal"].search_count([]), self.journal_count
        )
        self.assertEqual(self.xmlid.model, "account.journal")
        self.assertEqual(self.xmlid.res_id, self.journal.id)
        self.assertTrue(self.xmlid.noupdate)

    def _assert_legacy_reference_preserved(self):
        self._assert_journal_preserved()
        self.assertEqual(self.xmlid.module, "l10n_it_corrispettivi")
        self.assertEqual(self.xmlid.name, "corrispettivi_journal")
        self.assertEqual(
            self.env.ref("l10n_it_corrispettivi.corrispettivi_journal"), self.journal
        )
        self.assertFalse(
            self.env.ref(
                "account_receipt_journal.sale_receipts_journal",
                raise_if_not_found=False,
            )
        )

    def test_absent_legacy_module_leaves_journal_metadata_unchanged(self):
        rename_old_italian_data(self.env)
        self._assert_legacy_reference_preserved()

    def test_uninstalled_legacy_module_leaves_journal_metadata_unchanged(self):
        module = self.env["ir.module.module"].create(
            {"name": "l10n_it_corrispettivi", "state": "uninstalled"}
        )
        module.flush_recordset(["name", "state"])
        rename_old_italian_data(self.env)
        self._assert_legacy_reference_preserved()
        module.invalidate_recordset(["state"])
        self.assertEqual(module.state, "uninstalled")

    def test_installed_legacy_module_renames_reference_without_replacing_journal(self):
        module = self.env["ir.module.module"].create(
            {"name": "l10n_it_corrispettivi", "state": "installed"}
        )
        module.flush_recordset(["name", "state"])
        xmlid_id = self.xmlid.id
        rename_old_italian_data(self.env)
        self._assert_journal_preserved()
        self.assertEqual(self.xmlid.id, xmlid_id)
        self.assertEqual(self.xmlid.module, "account_receipt_journal")
        self.assertEqual(self.xmlid.name, "sale_receipts_journal")
        self.assertFalse(
            self.env.ref(
                "l10n_it_corrispettivi.corrispettivi_journal", raise_if_not_found=False
            )
        )
        self.assertEqual(
            self.env.ref("account_receipt_journal.sale_receipts_journal"), self.journal
        )
        module.invalidate_recordset(["state"])
        self.assertEqual(module.state, "installed")
