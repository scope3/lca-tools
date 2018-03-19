from lcatools.background.background import BackgroundEngine
from lcatools.exchanges import ExchangeValue, comp_dir


class TerminationNotFound(Exception):
    pass


class BackgroundManager(object):
    """
    Provides Lc access to matrix inversion results from a BackgroundEngine.  Acts as the content generator for
    BackgroundInterface.

    Abstracts the actual entities? do we pass entities or external_refs? TBD.

    BackgroundEngine needs to figure out the following:
     - list of foreground and background ProductFlows (terminations), and cutoff exterior flows (flow + direction)
    """
    def __init__(self, index_interface, quiet=True):
        """
        :param index_interface: passed thru to background engine
        """
        self._be = BackgroundEngine(index_interface, quiet=quiet)

    def re_index(self):
        self._be.fg.re_index()

    def _get_product_flow(self, process, ref_flow):
        rx = process.reference(flow=ref_flow)
        pf = self._be.add_ref_product(rx.flow, process)
        if pf is None:
            raise TerminationNotFound('Background Engine could not match ref_flow %s\nwith process %s' %
                                      (ref_flow, process))
        return pf

    def _ensure_background(self):
        """
        adds product flows until a background exists
        :return:
        """
        _pgen = self._be.fg.processes()
        while self._be.tstack.background is None:
            self._get_product_flow(next(_pgen), None)

    def _ensure_foreground(self):
        self._be.add_all_ref_products()

    @property
    def background_flows(self, *args):
        self._ensure_background()
        for k in self._be.background_flows(*args):
            yield k

    @property
    def foreground_flows(self, *args):
        self._ensure_foreground()
        for k in self._be.foreground_flows(*args):
            yield k

    @property
    def exterior_flows(self):
        self._ensure_background()
        for k in self._be.emissions:
            yield k

    def is_in_background(self, process, ref_flow=None):
        product_flow = self._get_product_flow(process, ref_flow=ref_flow)
        return self._be.is_in_background(product_flow)

    def product_flow(self, process, ref_flow=None):
        product_flow = self._get_product_flow(process, ref_flow=ref_flow)
        return ExchangeValue(product_flow.process, product_flow.flow, product_flow.direction, value=1.0)

    def foreground(self, process, ref_flow=None):
        """
        Returns a list of terminated exchanges beginning with the named process and reference flow, and containing
        the entire foreground (product system model). Dependencies and emissions are not included.
        :param process:
        :param ref_flow:
        :return:
        """
        product_flow = self._get_product_flow(process, ref_flow)
        fg = self._be.foreground(product_flow)
        _af, _ad, _bf = self._be.make_foreground(product_flow)

        # first, reference flow
        yield ExchangeValue(product_flow.process, product_flow.flow, product_flow.direction, value=1.0)

        # then, child fragments
        rows, cols = _af.nonzero()
        for i in range(len(rows)):
            node = fg[cols[i]]
            term = fg[rows[i]]
            yield ExchangeValue(node.process, term.flow, comp_dir(term.direction), value=_af.data[i],
                                termination=term.process.external_ref)

        '''
        if 0:
            # need to figure this out but for now we just want Af
            # next, dependencies
            rows, cols = _ad.nonzero()
            for i in range(len(rows)):
                node = fg[cols[i]]
                term = self._be.tstack.bg_node(rows[i])
                exchs.append(ExchangeValue(node.process, term.flow, comp_dir(term.direction), value=_ad.data[i],
                                           termination=term.process.external_ref))

            # last, fg emissions
            rows, cols = _bf.nonzero()
            for i in range(len(rows)):
                node = fg[cols[i]]
                emis = self._be.emissions[rows[i]]
                exchs.append(ExchangeValue(node.process, emis.flow, emis.direction, value=_bf.data[i]))

        return exchs
        '''

    def _background_dependencies(self, bg_product_flow):
        _, _ad, _ = self._be.make_foreground(bg_product_flow)
        rows, cols = _ad.nonzero()
        for i in range(len(rows)):
            assert cols[i] == 0
            term = self._be.tstack.bg_node(rows[i])
            yield ExchangeValue(bg_product_flow.process, term.flow, comp_dir(term.direction), value=_ad.data[i],
                                termination=term.process.external_ref)

    def _background_emissions(self, bg_product_flow):
        _, _, _bf = self._be.make_foreground(bg_product_flow)
        rows, cols = _bf.nonzero()
        for i in range(len(rows)):
            assert cols[i] == 0
            emis = self._be.emissions[rows[i]]
            yield ExchangeValue(bg_product_flow.process, emis.flow, emis.direction, value=_bf.data[i])

    def dependencies(self, process, ref_flow=None):
        """
        Return a single node's direct dependencies (A_d or A) as a list of exchanges
        :param process:
        :param ref_flow:
        :return:
        """
        pf = self._get_product_flow(process, ref_flow)
        if self._be.is_in_background(pf):
            for em in self._background_dependencies(pf):
                yield em

        else:
            for dep in self._be.foreground_dependencies(pf):  # dep isa MatrixEntry
                if not self.is_in_background(dep.term.process, dep.term.flow):
                    continue
                dat = dep.value
                dirn = 'Output' if dat < 0 else 'Input'
                yield ExchangeValue(dep.parent.process, dep.term.flow, dirn, value=dat,
                                    termination=dep.term.process.external_ref)

    def emissions(self, process, ref_flow=None):
        """
        Return a single node's direct emissions (B_f or B) as a list of exchanges
        :param process:
        :param ref_flow:
        :return:
        """
        pf = self._get_product_flow(process, ref_flow)
        if self._be.is_in_background(pf):
            for em in self._background_emissions(pf):
                yield em

        else:
            for em in self._be.foreground_emissions(pf):  # em isa CutoffEntry
                yield ExchangeValue(em.parent.process, em.emission.flow, em.emission.direction, value=em.value)

    def inventory(self, process, ref_flow=None, show=None):
        """
        Report the direct dependencies and exterior flows for the named product flow.  If the second argument is
        non-None, print the inventory instead of returning it.
        This should be identical to product_flow.process.inventory() so WHY DID I WRITE IT??????
        ans: because it exposes the allocated matrix model. so it's not the same for allocated processes.
        :param process:
        :param ref_flow: required for multi-product case
        :param show: [None] if present, show rather than return the inventory.
        :return: a list of exchanges.
        """
        product_flow = self._get_product_flow(process, ref_flow)
        ref_ex = ExchangeValue(product_flow.process, product_flow.flow, product_flow.direction, value=1.0)
        ref_ex.set_ref(product_flow.process)
        interior = [ref_ex]
        exterior = []
        if self._be.is_in_background(product_flow):
            # need to index into background matrix
            _af, _ad, _bf = self._be.make_foreground(product_flow)
            for i, row in enumerate(_ad.nonzero()[0]):
                dep = self._be.tstack.bg_node(row)
                dat = _ad.data[i]
                if dat < 0:
                    dirn = 'Output'
                else:
                    dirn = 'Input'
                interior.append(ExchangeValue(product_flow.process, dep.flow, dirn, value=abs(dat)))
            for i, row in enumerate(_bf.nonzero()[0]):
                ems = self._be.emissions[row]
                dat = _bf.data[i]
                exterior.append(ExchangeValue(product_flow.process, ems.emission.flow, ems.emission.direction,
                                              value=dat))
        else:
            # need to simply access the sparse matrix entries
            for fg in self._be.foreground_dependencies(product_flow):
                dat = fg.value
                if dat < 0:
                    dirn = 'Output'
                else:
                    dirn = 'Input'
                interior.append(ExchangeValue(product_flow.process, fg.term.flow, dirn, value=dat))
            for em in self._be.foreground_emissions(product_flow):
                exterior.append(ExchangeValue(product_flow.process, em.emission.flow, em.emission.direction,
                                              value=em.value))
        if show is None:
            return interior + exterior
        else:
            for x in interior:
                print('%s' % x)
            print('Exterior')
            for x in exterior:
                print('%s' % x)

    def lci(self, process, ref_flow=None, **kwargs):
        """
        Wrapper for compute_lci, returns exchanges with flows (and characterizations) drawn from self.archive
        :param process:
        :param ref_flow: required for multi-product case
        :param kwargs: passed to iterative solver: threshold=1e-8, count=100
        :return: list of exchanges.
        """
        product_flow = self._get_product_flow(process, ref_flow)
        in_ex = process.reference(ref_flow).value  # LCI values get normalized by inbound exchange-- we must de-norm
        b = self._be.compute_lci(product_flow, **kwargs)  # comes back as a sparse vector
        for i, em in enumerate(self._be.emissions):
            if b[i, 0] != 0:
                yield ExchangeValue(product_flow.process, em.flow, em.direction, value=b[i, 0] * in_ex)
