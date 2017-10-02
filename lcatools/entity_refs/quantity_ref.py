from .base import EntityRef


class QuantityRef(EntityRef):
    """
    Quantities can lookup:
    """
    _etype = 'quantity'

    def unit(self):
        return self.reference_entity.unitstring

    @property
    def _addl(self):
        return self.unit()

    def is_lcia_method(self):
        ind = self._query.get_item(self.external_ref, 'Indicator')
        if ind is None:
            return False
        elif len(ind) == 0:
            return False
        return True

    def flowables(self, **kwargs):
        return self._query.flowables(quantity=self.external_ref, **kwargs)

    def factors(self, **kwargs):
        return self._query.factors(self.external_ref, **kwargs)


