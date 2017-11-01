from .base import EntityRef


class ProcessRef(EntityRef):
    """
    Processes can lookup:
    """
    _etype = 'process'

    @property
    def _addl(self):
        return self.__getitem__('SpatialScope')

    def __init__(self, *args, **kwargs):
        super(ProcessRef, self).__init__(*args, **kwargs)
        self._default_rx = None
        rxs = [rx for rx in self.references()]
        if len(rxs) == 1:
            self._default_rx = rxs[0].flow.external_ref

    def _show_ref(self):
        for i in self.references():
            print('reference: %s' % i)

    @property
    def default_rx(self):
        """
        The 'primary' reference exchange of a process CatalogRef.  This is an external_ref for a flow

        (- which is req. unique among references)
        :return:
        """
        return self._default_rx

    @default_rx.setter
    def default_rx(self, value):
        if not isinstance(value, str):
            if hasattr(value, 'external_ref'):
                value = value.external_ref
            elif hasattr(value, 'entity_type'):
                if value.entity_type == 'exchange':
                    value = value.flow.external_ref
        if value in [rx.flow.external_ref for rx in self.references()]:
            self._default_rx = value
        else:
            print('Not a valid reference exchange specification')

    def reference(self, flow=None):
        return next(x for x in self.references(flow=flow))

    def references(self, flow=None):
        for x in self.reference_entity:
            if flow is None:
                yield x
            else:
                if x.flow == flow:
                    yield x

    def _use_ref_exch(self, ref_flow):
        if ref_flow is None and self._default_rx is not None:
            ref_flow = self._default_rx
        return ref_flow

    '''
    Inventory queries
    '''
    def exchanges(self, **kwargs):
        return self._query.exchanges(self.external_ref, **kwargs)

    def exchange_values(self, flow, direction, termination=None, **kwargs):
        return self._query.exchange_values(self.external_ref, flow.external_ref, direction,
                                           termination=termination, **kwargs)

    def inventory(self, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.inventory(self.external_ref, ref_flow=ref_flow, **kwargs)

    def exchange_relation(self, ref_flow, exch_flow, direction, termination=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.exchange_relation(self.origin, self.external_ref, ref_flow.external_ref,
                                             exch_flow.external_ref, direction,
                                             termination=termination, **kwargs)

    def fg_lcia(self, lcia_qty, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.lcia(self.external_ref, ref_flow, lcia_qty, **kwargs)

    '''
    Background queries
    '''
    def foreground(self, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.foreground(self.external_ref, ref_flow=ref_flow, **kwargs)

    def is_in_background(self, termination=None, ref_flow=None, **kwargs):
        if termination is None:
            termination = self.external_ref
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.is_in_background(termination, ref_flow=ref_flow, **kwargs)

    def ad(self, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.ad(self.external_ref, ref_flow, **kwargs)

    def bf(self, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.bf(self.external_ref, ref_flow, **kwargs)

    def lci(self, ref_flow=None, **kwargs):
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.lci(self.external_ref, ref_flow, **kwargs)

    def bg_lcia(self, lcia_qty, ref_flow=None, **kwargs):
        """
        :param lcia_qty: should be a quantity ref (or qty), not an external ID
        :param ref_flow:
        :param kwargs:
        :return:
        """
        ref_flow = self._use_ref_exch(ref_flow)
        return self._query.bg_lcia(self.external_ref, lcia_qty, ref_flow=ref_flow, **kwargs)
