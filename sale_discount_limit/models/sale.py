# -*- coding: utf-8 -*-

from odoo import models,fields,api, _
from odoo.exceptions import UserError, ValidationError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.multi
    def action_confirm(self):
        if self.team_id and self.team_id.discount_limit:
            for record in self.mapped('order_line'):
                if self.team_id.discount_limit < record.discount:
                    raise UserError(_('Discount given for product %s is more then limit %s') % (record.product_id.name, self.team_id.discount_limit))
        return super(SaleOrder, self).action_confirm()

class Team(models.Model):
    _inherit = 'crm.team'

    discount_limit = fields.Float(string="Discount Limit")