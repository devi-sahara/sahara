# -*- coding: utf-8 -*-


{
    'name': 'Pricelist calculation base on second sale price',
    'version': '1.1',
    'summary': 'customization pricelist',
    'sequence': 30,
    'description': """
    """,
    'category': 'Pricelst Management',
    'depends': ['sale_management'],
    'data': [
        'views/inherit_price_list_view.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': False,
}
