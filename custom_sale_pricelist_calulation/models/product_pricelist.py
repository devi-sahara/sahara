# -*- coding: utf-8 -*-

from itertools import chain

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

from odoo.addons import decimal_precision as dp


class Pricelist(models.Model):
    _inherit = "product.pricelist"

    @api.multi
    def _compute_price_rule(self, products_qty_partner, date=False, uom_id=False):
        """ Low-level method - Mono pricelist, multi products
        Returns: dict{product_id: (price, suitable_rule) for the given pricelist}

        If date in context: Date of the pricelist (%Y-%m-%d)

            :param products_qty_partner: list of typles products, quantity, partner
            :param datetime date: validity date
            :param ID uom_id: intermediate unit of measure
        """
        self.ensure_one()
        if not date:
            date = self._context.get('date') or fields.Date.context_today(self)
        if not uom_id and self._context.get('uom'):
            uom_id = self._context['uom']
        if uom_id:
            # rebrowse with uom if given
            products = [item[0].with_context(uom=uom_id) for item in products_qty_partner]
            products_qty_partner = [(products[index], data_struct[1], data_struct[2]) for index, data_struct in
                                    enumerate(products_qty_partner)]
        else:
            products = [item[0] for item in products_qty_partner]

        if not products:
            return {}

        categ_ids = {}
        for p in products:
            categ = p.categ_id
            while categ:
                categ_ids[categ.id] = True
                categ = categ.parent_id
        categ_ids = list(categ_ids)

        is_product_template = products[0]._name == "product.template"
        if is_product_template:
            prod_tmpl_ids = [tmpl.id for tmpl in products]
            # all variants of all products
            prod_ids = [p.id for p in
                        list(chain.from_iterable([t.product_variant_ids for t in products]))]
        else:
            prod_ids = [product.id for product in products]
            prod_tmpl_ids = [product.product_tmpl_id.id for product in products]

        # Load all rules
        self._cr.execute(
            'SELECT item.id '
            'FROM product_pricelist_item AS item '
            'LEFT JOIN product_category AS categ '
            'ON item.categ_id = categ.id '
            'WHERE (item.product_tmpl_id IS NULL OR item.product_tmpl_id = any(%s))'
            'AND (item.product_id IS NULL OR item.product_id = any(%s))'
            'AND (item.categ_id IS NULL OR item.categ_id = any(%s)) '
            'AND (item.pricelist_id = %s) '
            'AND (item.date_start IS NULL OR item.date_start<=%s) '
            'AND (item.date_end IS NULL OR item.date_end>=%s)'
            'ORDER BY item.applied_on, item.min_quantity desc, categ.complete_name desc, item.id desc',
            (prod_tmpl_ids, prod_ids, categ_ids, self.id, date, date))
        # NOTE: if you change `order by` on that query, make sure it matches
        # _order from model to avoid inconstencies and undeterministic issues.

        item_ids = [x[0] for x in self._cr.fetchall()]
        items = self.env['product.pricelist.item'].browse(item_ids)
        results = {}
        for product, qty, partner in products_qty_partner:
            results[product.id] = 0.0
            suitable_rule = False

            # Final unit price is computed according to `qty` in the `qty_uom_id` UoM.
            # An intermediary unit price may be computed according to a different UoM, in
            # which case the price_uom_id contains that UoM.
            # The final price will be converted to match `qty_uom_id`.
            qty_uom_id = self._context.get('uom') or product.uom_id.id
            price_uom_id = product.uom_id.id
            qty_in_product_uom = qty
            if qty_uom_id != product.uom_id.id:
                try:
                    qty_in_product_uom = self.env['uom.uom'].browse([self._context['uom']])._compute_quantity(qty,
                                                                                                              product.uom_id)
                except UserError:
                    # Ignored - incompatible UoM in context, use default product UoM
                    pass

            # if Public user try to access standard price from website sale, need to call price_compute.
            # TDE SURPRISE: product can actually be a template
            price = product.price_compute('list_price')[product.id]

            price_uom = self.env['uom.uom'].browse([qty_uom_id])
            for rule in items:
                if rule.min_quantity and qty_in_product_uom < rule.min_quantity:
                    continue
                if is_product_template:
                    if rule.product_tmpl_id and product.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and not (
                            product.product_variant_count == 1 and product.product_variant_id.id == rule.product_id.id):
                        # product rule acceptable on template if has only one variant
                        continue
                else:
                    if rule.product_tmpl_id and product.product_tmpl_id.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and product.id != rule.product_id.id:
                        continue

                if rule.categ_id:
                    cat = product.categ_id
                    while cat:
                        if cat.id == rule.categ_id.id:
                            break
                        cat = cat.parent_id
                    if not cat:
                        continue

                if rule.base == 'pricelist' and rule.base_pricelist_id:
                    price_tmp = rule.base_pricelist_id._compute_price_rule([(product, qty, partner)])[product.id][
                        0]  # TDE: 0 = price, 1 = rule
                    price = rule.base_pricelist_id.currency_id._convert(price_tmp, self.currency_id,
                                                                        self.env.user.company_id, date, round=False)
                else:
                    # if base option is public price take sale price else cost price of product
                    # price_compute returns the price in the context UoM, i.e. qty_uom_id
                    price = product.price_compute(rule.base)[product.id]

                convert_to_price_uom = (lambda price: product.uom_id._compute_price(price, price_uom))

                if price is not False:
                    if rule.compute_price == 'fixed':
                        price = convert_to_price_uom(rule.fixed_price)
                    elif rule.compute_price == 'percentage':
                        price = (price - (price * (rule.percent_price / 100))) or 0.0
                    # compute second sale price
                    elif rule.compute_price == 'second_sale':
                        price = convert_to_price_uom(rule.second_sale_price)

                    else:
                        # complete formula
                        price_limit = price
                        price = (price - (price * (rule.price_discount / 100))) or 0.0
                        if rule.price_round:
                            price = tools.float_round(price, precision_rounding=rule.price_round)

                        if rule.price_surcharge:
                            price_surcharge = convert_to_price_uom(rule.price_surcharge)
                            price += price_surcharge

                        if rule.price_min_margin:
                            price_min_margin = convert_to_price_uom(rule.price_min_margin)
                            price = max(price, price_limit + price_min_margin)

                        if rule.price_max_margin:
                            price_max_margin = convert_to_price_uom(rule.price_max_margin)
                            price = min(price, price_limit + price_max_margin)
                    suitable_rule = rule
                break
            # Final price conversion into pricelist currency
            if suitable_rule and suitable_rule.compute_price != 'fixed' and suitable_rule.base != 'pricelist':
                if suitable_rule.base == 'standard_price':
                    cur = product.cost_currency_id
                else:
                    cur = product.currency_id
                price = cur._convert(price, self.currency_id, self.env.user.company_id, date, round=False)

            results[product.id] = (price, suitable_rule and suitable_rule.id or False)

        return results

class PricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    compute_price = fields.Selection([
        ('fixed', 'Fix Price'),
        ('percentage', 'Percentage (discount)'),
        ('formula', 'Formula'),
        ('second_sale', 'Apply on second Sale Price')], index=True, default='fixed')
    second_sale_price = fields.Float('Fixed Price', digits=dp.get_precision('Product Price'))
    name = fields.Char(
        'Name', compute='_get_pricelist_item_name_price',
        help="Explicit rule name for this pricelist line.")
    price = fields.Char(
        'Price', compute='_get_pricelist_item_name_price',
        help="Explicit rule name for this pricelist line.")

    @api.one
    @api.depends('categ_id', 'product_tmpl_id', 'product_id', 'compute_price', 'fixed_price', \
                 'pricelist_id', 'percent_price', 'price_discount', 'price_surcharge')
    def _get_pricelist_item_name_price(self):
        if self.categ_id:
            self.name = _("Category: %s") % (self.categ_id.name)
        elif self.product_tmpl_id:
            self.name = self.product_tmpl_id.name
        elif self.product_id:
            self.name = self.product_id.display_name.replace('[%s]' % self.product_id.code, '')
        else:
            self.name = _("All Products")

        if self.compute_price == 'fixed':
            self.price = ("%s %s") % (self.fixed_price, self.pricelist_id.currency_id.name)
        elif self.compute_price == 'percentage':
            self.price = _("%s %% discount") % (self.percent_price)

        # name update base on the second sale price
        if self.compute_price == 'second_sale':
            self.price = ("%s %s") % (self.second_sale_price, self.pricelist_id.currency_id.name)
        else:
            self.price = _("%s %% discount and %s surcharge") % (self.price_discount, self.price_surcharge)


    @api.onchange('compute_price')
    def _onchange_compute_price(self):
        res = super(PricelistItem, self)._onchange_compute_price()
        if self.compute_price != 'second_sale':
            self.second_sale_price = 0.0
        return res

