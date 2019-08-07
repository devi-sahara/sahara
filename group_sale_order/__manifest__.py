{
    'name': 'Special UOM rights',
    'version':'1.0', 
    'category': 'Sales',
    'summary': 'Special UOM rights',
    'description' : ''' Special UOM rights ''',
    'depends': ['sale_management'],
    'data': [
        'security/special_uom_writes.xml',
        'views/sale_view.xml',
    ],
    'application': True,
    'installable': True,
    'auto-install': False
}