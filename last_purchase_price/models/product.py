# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
import odoo.addons.decimal_precision as dp

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    last_purchase_price = fields.Float(string='Last Cost Price', digits=dp.get_precision('Product Price'))

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.multi
    def button_confirm(self):
        for line in self.mapped('order_line'):
            line.product_id.last_purchase_price = line.price_unit
        return super(PurchaseOrder, self).button_confirm()