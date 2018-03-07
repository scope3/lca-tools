from .catalog_query import CatalogQuery, PrivateArchive, EntityNotFound

from .iconfigure import ConfigureInterface
from .iinventory import InventoryInterface, InventoryRequired
from .iindex import IndexInterface
from .ibackground import BackgroundInterface, BackgroundRequired
from .iquantity import QuantityInterface
from .iforeground import ForegroundInterface, ForegroundRequired

import re


def trim_cas(cas):
    try:
        return re.sub('^(0*)', '', cas)
    except TypeError:
        print('%s %s' % (cas, type(cas)))
        return ''
