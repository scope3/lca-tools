from .basic import BasicImplementation
from lcatools.interfaces import InventoryInterface, PrivateArchive


class InventoryImplementation(BasicImplementation, InventoryInterface):
    """
    This provides access to detailed exchange values and computes the exchange relation.
    Creates no additional requirements on the archive.
    """
    def exchanges(self, process, **kwargs):
        if self.privacy > 1:
            raise PrivateArchive('Exchange lists are protected')
        p = self._archive.retrieve_or_fetch_entity(process)
        for x in p.exchanges():
            yield x

    def exchange_values(self, process, flow, direction, termination=None, **kwargs):
        if self.privacy > 0:
            raise PrivateArchive('Exchange values are protected')
        p = self._archive.retrieve_or_fetch_entity(process)
        for x in p.exchange_values(self.get(flow), direction=direction):
            if termination is None:
                yield x
            else:
                if x.termination == termination:
                    yield x

    def inventory(self, process, ref_flow=None, scenario=None, **kwargs):
        if self.privacy > 0:
            raise PrivateArchive('Exchange values are protected')
        p = self._archive.retrieve_or_fetch_entity(process)
        if p.entity_type == 'process':
            for x in sorted(p.inventory(reference=ref_flow),
                            key=lambda t: (not t.is_reference, t.direction, t.value or 0.0)):
                yield x
        elif p.entity_type == 'fragment':
            for x in p.inventory(scenario=scenario, observed=True):
                yield x

    def exchange_relation(self, process, ref_flow, exch_flow, direction, termination=None, **kwargs):
        """

        :param process:
        :param ref_flow:
        :param exch_flow:
        :param direction:
        :param termination:
        :return:
        """
        if self.privacy > 0:
            raise PrivateArchive('Exchange values are protected')
        p = self._archive.retrieve_or_fetch_entity(process)
        xs = [x for x in p.inventory(reference=ref_flow)
              if x.flow.external_ref == exch_flow and x.direction == direction]
        norm = p.reference(ref_flow)
        if termination is not None:
            xs = [x for x in xs if x.termination == termination]
        if len(xs) == 1:
            return xs[0].value / norm.value
        elif len(xs) == 0:
            return 0.0
        else:
            return sum([x.value for x in xs]) / norm.value

    def lcia(self, process, ref_flow, quantity_ref, refresh=False, **kwargs):
        """
        Implementation of foreground LCIA -- moved from LcCatalog
        :param process:
        :param ref_flow:
        :param quantity_ref:
        :param refresh:
        :param kwargs:
        :return:
        """
        return quantity_ref.do_lcia(process.inventory(ref_flow=ref_flow),
                                    locale=process['SpatialScope'],
                                    refresh=refresh)
