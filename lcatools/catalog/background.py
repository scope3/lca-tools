import re
from lcatools.background.background_manager import BackgroundManager
from lcatools.background.proxy import BackgroundProxy
from lcatools.background.product_flow import ProductFlow
from lcatools.background.emission import Emission
from lcatools.catalog.basic import BasicInterface


class NonStaticBackground(Exception):
    pass


class BackgroundInterface(BasicInterface):
    """
    The BackgroundInterface exposes LCI computation with matrix ordering and inversion, and LCIA computation with
    enclosed private access to a quantity db.
    """
    def __init__(self, archive, qdb, **kwargs):
        super(BackgroundInterface, self).__init__(archive, **kwargs)
        self._qdb = qdb

        self._bm = None

    def _make_pf_ref(self, product_flow):
        return ProductFlow(None, self.make_ref(product_flow.process), product_flow.flow)

    @property
    def _bg(self):
        """
        The background is provided either by a BackgroundManager (wrapper for BackgroundEngine matrix inverter)
        or by a BackgroundProxy (assumes archive is already aggregated)
        :return:
        """
        if self._bm is None:
            if self._archive.static:
                # perform costly operations only when/if required
                self._bm = BackgroundManager(self._archive)  # resources only accessible from a BackgroundInterface
            else:
                # non-static interfaces implement foreground-as-background
                self._bm = BackgroundProxy(self._archive)
        return self._bm

    '''
    foreground compat methods
    '''

    def get(self, eid):
        return self.make_ref(self._archive.retrieve_or_fetch_entity(eid))

    def exchange_values(self, process, flow, direction, termination=None):
        """
        Just yield reference exchanges through the foreground interface
        :param process:
        :param flow:
        :param direction:
        :param termination:
        :return:
        """
        if termination is not None:
            raise TypeError('Reference exchanges cannot be terminated')
        p = self._archive.retrieve_or_fetch_entity(process)
        for x in p.reference_entity:
            if x.flow.external_ref == flow and x.direction == direction:
                yield x

    '''
    background managed methods
    '''
    def foreground(self, process, ref_flow=None):
        p = self._archive.retrieve_or_fetch_entity(process)
        if ref_flow is not None:
            ref_flow = self._archive.retrieve_or_fetch_entity(ref_flow)
        return self._bg.foreground(p, ref_flow=ref_flow)

    def foreground_flows(self, search=None):
        for k in self._bg.foreground_flows:
            if search is None:
                yield self._make_pf_ref(k)
            else:
                if bool(re.search(search, str(k), flags=re.IGNORECASE)):
                    yield self._make_pf_ref(k)

    def background_flows(self, search=None):
        for k in self._bg.background_flows:
            if search is None:
                yield self._make_pf_ref(k)
            else:
                if bool(re.search(search, str(k), flags=re.IGNORECASE)):
                    yield self._make_pf_ref(k)

    def exterior_flows(self, direction=None, search=None):
        for k in self._bg.exterior_flows:
            if direction is not None:
                if k.direction != direction:
                    continue
            if search is not None:
                if not bool(re.search(search, str(k), flags=re.IGNORECASE)):
                    continue
            yield k

    def cutoffs(self, direction=None, search=None):
        for k in self._bg.exterior_flows:
            if self._qdb.is_elementary(k):
                continue
            if direction is not None:
                if k.direction != direction:
                    continue
            if search is not None:
                if not bool(re.search(search, str(k), flags=re.IGNORECASE)):
                    continue
            yield k

    def emissions(self, direction=None, search=None):
        for k in self._bg.exterior_flows:
            if not self._qdb.is_elementary(k):
                continue
            if direction is not None:
                if k.direction != direction:
                    continue
            if search is not None:
                if not bool(re.search(search, str(k), flags=re.IGNORECASE)):
                    continue
            yield k

    def lci(self, process, ref_flow=None):
        p = self._archive.retrieve_or_fetch_entity(process)
        if ref_flow is not None:
            ref_flow = self._archive.retrieve_or_fetch_entity(ref_flow)
        return self._bg.lci(p, ref_flow=ref_flow)

    def ad(self, process, ref_flow=None):
        if ref_flow is not None:
            ref_flow = self._archive.retrieve_or_fetch_entity(ref_flow)
        return self._bg.ad_tilde(process, ref_flow=ref_flow)

    def bf(self, process, ref_flow=None):
        if ref_flow is not None:
            ref_flow = self._archive.retrieve_or_fetch_entity(ref_flow)
        return self._bg.bf_tilde(process, ref_flow=ref_flow)

    def bg_lcia(self, process, query_qty, ref_flow=None, **kwargs):
        p = self._archive.retrieve_or_fetch_entity(process)
        if ref_flow is not None:
            ref_flow = self._archive.retrieve_or_fetch_entity(ref_flow)
        q = self._qdb.get_canonical_quantity(query_qty)  #
        if self._archive.static:
            if not self.is_characterized(q):
                self.characterize(self._qdb, q, **kwargs)
            return self._bg.lcia(p, query_qty, ref_flow=ref_flow)
        else:
            lci = self._bg.lci(p, ref_flow=ref_flow)
            return self._qdb.do_lcia(q, lci, locale=p['SpatialScope'])
