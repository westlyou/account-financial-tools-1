# -*- coding: utf-8 -*-
from openerp import tools
from openerp import models, fields, api
from ast import literal_eval


class AccountDebtLine(models.Model):
    _name = "account.debt.line"
    _description = "Account Debt Line"
    _auto = False
    _rec_name = 'document_number'
    _order = 'date asc, date_maturity asc, document_number asc, id'
    _depends = {
        'res.partner': [
            'user_id',
        ],
        'account.move': [
            'document_type_id', 'document_number',
        ],
        'account.move.line': [
            'account_id', 'debit', 'credit', 'date_maturity', 'partner_id',
            'amount_currency',
        ],
    }

    document_type_id = fields.Many2one(
        'account.document.type',
        'Document Type',
        readonly=True
    )
    document_number = fields.Char(
        readonly=True,
        string='Document Number',
    )
    date = fields.Date(
        readonly=True
    )
    date_maturity = fields.Date(
        readonly=True
    )
    ref = fields.Char(
        'Reference',
        readonly=True
    )
    amount = fields.Monetary(
        readonly=True,
        currency_field='company_currency_id',
    )
    amount_residual = fields.Monetary(
        readonly=True,
        string='Residual Amount',
        currency_field='company_currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        'Currency',
        readonly=True
    )
    amount_currency = fields.Monetary(
        readonly=True,
        currency_field='currency_id',
    )
    amount_residual_currency = fields.Monetary(
        readonly=True,
        string='Residual Amount in Currency',
        currency_field='currency_id',
    )
    move_lines_str = fields.Char(
        'Entry Lines String',
        readonly=True
    )
    account_id = fields.Many2one(
        'account.account',
        'Account',
        readonly=True
    )
    internal_type = fields.Selection([
        ('receivable', 'Receivable'),
        ('payable', 'Payable')],
        'Type',
        readonly=True,
    )
    # move_state = fields.Selection(
    #     [('draft', 'Unposted'), ('posted', 'Posted')],
    #     'Status',
    #     readonly=True
    # )
    reconciled = fields.Boolean(
    )
    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
        readonly=True
    )
    account_type = fields.Many2one(
        'account.account.type',
        'Account Type',
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        readonly=True
    )

    # computed fields
    financial_amount = fields.Monetary(
        compute='_compute_move_lines_data',
        readonly=True,
        currency_field='company_currency_id',
    )
    financial_amount_residual = fields.Monetary(
        compute='_compute_move_lines_data',
        currency_field='company_currency_id',
        readonly=True,
    )
    move_line_ids = fields.One2many(
        'account.move.line',
        string='Entry lines',
        compute='_compute_move_lines_data',
        readonly=True
    )
    move_ids = fields.One2many(
        'account.move',
        string='Entry',
        compute='_compute_move_lines_data',
        readonly=True
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )

    # TODO por ahora, y si nadie lo extraña, vamos a usar document_number
    # en vez de este, alternativas por si se extraña:
    # si se extraña entonces tal vez mejor restaurarlo con otro nombre
    # @api.one
    # def get_display_name(self):
    #     # usamos display_name para que contenga doc number o name
    #     # luego si el ref es igual al name del move no lo mostramos
    #     display_name = self.move_id.display_name
    #     ref = False
    #     # because account voucher replace / with ''
    #     move_names = [self.move_id.name, self.move_id.name.replace('/', '')]
    #     # solo agregamos el ref del asiento o el name del line si son
    #     # distintos a el name del asiento
    #     if self.ref and self.ref not in move_names:
    #         ref = self.ref
    #     elif (
    #             self.move_line_id.name and
    #             self.move_line_id.name != '/' and
    #             self.move_line_id.name not in move_names):
    #         ref = self.move_line_id.name
    #     if ref:
    #         display_name = '%s (%s)' % (display_name, ref)
    #     self.display_name = display_name

    @api.multi
    @api.depends('move_lines_str')
    # @api.depends('amount', 'amount_currency')
    def _compute_move_lines_data(self):
        """
        If debt_together in context then we discount payables and make
        cumulative all together
        """
        for rec in self:
            rec.move_line_ids = rec.move_line_ids.browse(
                literal_eval(rec.move_lines_str))
            rec.move_ids = rec.move_line_ids.mapped('move_id')
            rec.financial_amount = sum(
                rec.move_line_ids.mapped('financial_amount'))
            rec.financial_amount_residual = sum(
                rec.move_line_ids.mapped('financial_amount_residual'))

    def init(self, cr):
        tools.drop_view_if_exists(cr, self._table)
        query = """
            SELECT
                row_number() OVER () AS id,
                string_agg(cast(l.id as varchar), ',') as move_lines_str,
                max(am.date) as date,
                max(l.date_maturity) as date_maturity,
                am.document_type_id as document_type_id,
                c.document_number as document_number,
                bool_and(l.reconciled) as reconciled,

                -- TODO borrar, al final no pudimos hacerlo asi porque si no
                -- agrupamos por am.name, entonces todo lo que no tenga tipo
                -- de doc lo muestra en una linea. Y si lo agregamos nos quedan
                -- desagregados los multiples pagos (y otros similares)
                -- si devuelve '' el concat del prefix y number lo cambiamos
                -- por null y luego coalesce se encarga de elerig el name
                -- devolvemos el string_agg de am.name para no tener que
                -- agregarlo en la clausula del group by
                -- COALESCE(NULLIF(CONCAT(
                --     dt.doc_code_prefix, am.document_number), ''),
                --         string_agg(am.name, ',')) as document_number,

                string_agg(am.ref, ',') as ref,
                --am.state as move_state,
                --l.full_reconcile_id as full_reconcile_id,
                --l.reconciled as reconciled,
                -- l.reconcile_partial_id as reconcile_partial_id,
                l.partner_id as partner_id,
                am.company_id as company_id,
                a.internal_type as internal_type,
                -- am.journal_id as journal_id,
                -- p.fiscalyear_id as fiscalyear_id,
                -- am.period_id as period_id,
                l.account_id as account_id,
                --l.analytic_account_id as analytic_account_id,
                -- a.internal_type as type,
                a.user_type_id as account_type,
                l.currency_id as currency_id,
                sum(l.amount_currency) as amount_currency,
                sum(l.amount_residual_currency) as amount_residual_currency,
                sum(l.amount_residual) as amount_residual,
                --pa.user_id as user_id,
                sum(l.balance) as amount
                -- coalesce(l.debit, 0.0) - coalesce(l.credit, 0.0) as amount
            FROM
                account_move_line l
                left join account_account a on (l.account_id = a.id)
                left join account_move am on (am.id=l.move_id)
                -- left join account_period p on (am.period_id=p.id)
                left join res_partner pa on (l.partner_id=pa.id)
                left join account_document_type dt on (
                    am.document_type_id=dt.id)
                left join (
                    SELECT
                        COALESCE (NULLIF (CONCAT (
                            dt.doc_code_prefix, am.document_number), ''),
                            am.name) as document_number,
                        am.id
                    FROM
                        account_move am
                        left join account_document_type dt on (
                            am.document_type_id=dt.id)
                    ) c on l.move_id = c.id
            WHERE
                -- l.state != 'draft' and
                a.internal_type IN ('payable', 'receivable')
            GROUP BY
                l.partner_id, am.company_id, l.account_id, l.currency_id,
                a.internal_type, a.user_type_id, c.document_number,
                am.document_type_id
                -- dt.doc_code_prefix, am.document_number
        """
        cr.execute("""CREATE or REPLACE VIEW %s as (%s
        )""" % (self._table, query))

    @api.multi
    def action_open_related_document(self):
        self.ensure_one()
        view_id = False
        # TODO ver si queremos devolver lista si hay mas de uno
        record = self.env['account.invoice'].search(
            [('move_id', '=', self.move_id.id)], limit=1)
        if not record:
            record = self.env['account.payment'].search(
                [('move_line_ids', '=', self.id)], limit=1)
            if record:
                view_id = self.env['ir.model.data'].xmlid_to_res_id(
                    'account.view_account_payment_form')
            else:
                record = self.move_id
        else:
            # if invoice, we choose right view
            if record.type in ['in_refund', 'in_invoice']:
                view_id = self.env.ref('account.invoice_supplier_form').id
            else:
                view_id = self.env.ref('account.invoice_form').id

        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': record.id,
            'view_id': view_id,
        }
