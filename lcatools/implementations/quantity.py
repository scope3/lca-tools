from synlist import Flowables, InconsistentIndices

from .basic import BasicImplementation
from lcatools.interfaces.iquantity import QuantityInterface


class QuantityImplementation(BasicImplementation, QuantityInterface):
    """
    Unlike entity, foreground, and background interfaces, a quantity interface does not require a static archive
    (since there are no terminations to index) or a background manager (since there are no processes)

    The quantity interface requires a compartment manager to function.

    The interface works normally on normally-constituted archives, but also allows the archives to override the default
    implementations (which require load_all)
    """
    def __init__(self, catalog, archive, **kwargs):
        super(QuantityImplementation, self).__init__(catalog, archive, **kwargs)
        self._cm = catalog.qdb.c_mgr
        self._flowables = None
        self._compartments = dict()

    def _init_flowables(self):
        fb = Flowables()
        for f in self._archive.flows():
            c = f['CasNumber']
            n = f['Name']
            try:
                fb.add_synonyms(c, n)
                fb.set_name(n)
            except InconsistentIndices:
                fb.merge(c, n)
            fb.add_synonyms(n, f.link)
        return fb

    @property
    def _fb(self):
        if self._flowables is None:
            if self._archive.static:
                if not hasattr(self._archive, 'fb'):
                    self._archive.fb = self._init_flowables()
                self._flowables = self._archive.fb
            else:
                print('Non-static archive. need to override flowables.')
                self._flowables = self._init_flowables()  # this will not really work.
        return self._flowables

    def quantities(self, **kwargs):
        for q_e in self._archive.quantities(**kwargs):
            q_ref = self.make_ref(q_e)
            yield q_ref

    def lcia_methods(self, **kwargs):
        for l in self._archive.lcia_methods(**kwargs):
            l_ref = self.make_ref(l)
            yield l_ref

    def _check_compartment(self, string):
        if string is None:
            return None
        if string in self._compartments:
            return self._compartments[string]
        c = self._cm.find_matching(string)
        self._compartments[string] = c
        return c

    def get_quantity(self, quantity, **kwargs):
        """
        Retrieve a canonical quantity from a qdb
        :param quantity: external_id of quantity
        :return: quantity entity
        """
        if hasattr(self._archive, 'get_quantity'):
            return self.make_ref(self._archive.get_quantity(quantity))
        return self.make_ref(self._archive[quantity])

    def synonyms(self, item, **kwargs):
        """
        Return a list of synonyms for the object -- quantity, flowable, or compartment
        :param item:
        :return: list of strings
        """
        if hasattr(self._archive, 'synonyms'):
            return self._archive.synonyms(item)
        raise NotImplemented

    def flowables(self, quantity=None, compartment=None, **kwargs):
        """
        Return a list of flowable strings. Use quantity and compartment parameters to narrow the result
        set to those characterized by a specific quantity, those exchanged with a specific compartment, or both
        :param quantity:
        :param compartment:
        :return: list of pairs: CAS number, name
        """
        if hasattr(self._archive, 'flowables'):
            for n in self._archive.flowables(quantity=quantity, compartment=compartment):
                yield n
        else:
            compartment = self._check_compartment(compartment)
            if quantity is not None:
                quantity = self._archive[quantity]
            fb = set()
            for f in self._archive.flows():
                if compartment is not None:
                    if self._check_compartment(f['Compartment']) is not compartment:
                        continue
                if quantity is not None:
                    if not f.has_characterization(quantity):
                        continue
                fb.add(self._fb.index(f['Name']))
            for n in sorted(list(fb), key=lambda x: self._fb.name(x)):
                yield self._fb.cas(n), self._fb.name(n)

    def compartments(self, quantity=None, flowable=None, **kwargs):
        """
        Return a list of compartment strings. Use quantity and flowable parameters to narrow the result
        set to those characterized for a specific quantity, those with a specific flowable, or both
        :param quantity:
        :param flowable:
        :return: list of strings
        """
        if hasattr(self._archive, 'compartments'):
            for n in self._archive.compartments(quantity=quantity, flowable=flowable):
                yield n
        else:
            comps = set()
            for f in self._archive.flows():
                comps.add(self._check_compartment(f['Compartment']))
            for n in comps:
                yield str(n)

    def factors(self, quantity, flowable=None, compartment=None, **kwargs):
        """
        Return characterization factors for the given quantity, subject to optional flowable and compartment
        filter constraints. This is ill-defined because the reference unit is not explicitly reported in current
        serialization for characterizations (it is implicit in the flow)-- but it can be added to a web service layer.

        This uses flow.has_characterization() so the argument needs to be converted to the strictly internal quantity
        entity from the local _archive.
        :param quantity:
        :param flowable:
        :param compartment:
        :return:
        """
        if hasattr(self._archive, 'factors'):
            for n in self._archive.factors(quantity, flowable=flowable, compartment=compartment):
                yield n
        else:
            if isinstance(quantity, str):
                quantity = self.get_quantity(quantity)
            int_q = self._archive[quantity.external_ref]  # the truly local quantity
            if flowable is not None:
                flowable = self._fb.index(flowable)
            compartment = self._cm.find_matching(compartment)
            for f in self._archive.flows():
                if not f.has_characterization(int_q):
                    continue
                if flowable is not None:
                    if self._fb.index(f.link) != flowable:
                        continue
                if compartment is not None:
                    if self._cm.find_matching(f['Compartment']) != compartment:
                        continue
                yield f.factor(int_q)

    def quantity_relation(self, ref_quantity, flowable, compartment, query_quantity, locale='GLO', **kwargs):
        """
        Return a single number that converts the a unit of the reference quantity into the query quantity for the
        given flowable, compartment, and locale (default 'GLO').  If no locale is found, this would be a great place
        to run a spatial best-match algorithm.
        :param ref_quantity:
        :param flowable:
        :param compartment:
        :param query_quantity:
        :param locale:
        :return:
        """
        if hasattr(self._archive, 'quantity_relation'):
            return self._archive.quantity_relation(ref_quantity, flowable, compartment, query_quantity, locale=locale)
        raise NotImplemented  # must be overridden