"""
Contexts in this sense are environmental compartments, except they have the added capability to keep lists of origins.

Edelen and Ingwersen et al 2017:
"Recommendations: ...setting an exclusive or inclusive nomenclature for flow context information that includes
directionality and environmental compartment information."

In the antelope architecture, there are two different objectives for handling contexts as-presented by the data source.

 In the default case, for every static resource or stand-alone archive a "TermManager" is created which is captive to
 the archive.  The role of this class is to collect information from the data source in as close to its native
 presentation as possible. This creates an "inclusive" nomenclature for the source.

 In the Catalog case, both catalog's local quantity DB is an LciaEngine, which is also shared among all non-static
 resources (including remote resources).  In this case the objective is to match a given context to the existing
 (exclusive) nomenclature built-in to the LciaEngine, so that contexts are guaranteed to coincide during LCIA.

In order to accomplish this, the native add_context() method needs to be expansive, fault tolerant, and widely accepting
of diverse inputs, whereas find_matching_context() needs to be more discerning and rigorous.
"""

from synonym_dict.example_compartments import Compartment, CompartmentManager

ELEMENTARY = {'resources', 'emissions'}

PROTECTED = ('air', 'water', 'ground')

class ProtectedTerm(Exception):
    pass


class InvalidSense(Exception):
    pass


class InconsistentSense(Exception):
    pass


class FrozenElementary(Exception):
    """
    top-level elementary contexts may not be assigned parents
    """
    pass


def valid_sense(sense):
    if sense is None:
        return None
    try:
        v = {'source': 'Source',
             'sink': 'Sink'}[sense.lower()]
    except KeyError:
        raise InvalidSense(sense)
    return v


def _dir_mod(arg, sense):
    mod = {'Source': 'from', 'Sink': 'to'}[sense]
    if arg.lower() in PROTECTED:
        arg = '%s %s' % (mod, arg)
    return arg


class Context(Compartment):
    """
    A context has a natural directional "sense", which is either 'Source', 'Sink', or None.  A Source context
    generates flows which may be inputs to the activity; a Sink context absorbs flows which are output from the
    activity.

    If a context has a parent, it inherits the sense of the parent- specifying the opposite sense will raise
    an error.
    """
    _origins = set()
    entity_type = 'context'

    def __init__(self, *args, sense=None, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self._sense = None
        if sense is not None:
            self.sense = sense

    @property
    def sense(self):
        if self.parent is None:
            return self._sense
        return self.parent.sense

    @sense.setter
    def sense(self, value):
        sense = valid_sense(value)
        if self.sense is not None and self.sense != sense:
            raise InconsistentSense('Value %s conflicts with current sense %s' % (sense, self.sense))
        if self.parent is None:
            self._sense = valid_sense(value)
        else:
            self.parent.sense = value

    @property
    def parent(self):  # duplicating here to override setter
        return self._parent

    @parent.setter
    def parent(self, parent):
        if self._parent is not None:
            self._parent.deregister_subcompartment(self)
        else:
            if self.elementary and not parent.elementary:
                raise FrozenElementary
        self._parent = parent
        if parent is not None:
            parent.register_subcompartment(self)

    @property
    def elementary(self):
        if self.parent is None:
            for t in self.terms:
                if t.strip().lower() in ELEMENTARY:
                    return True
            return False
        else:
            return self.parent.elementary

    @property
    def seq(self):
        if self.parent is None:
            return [self]
        return self.parent.seq + [self]

    @property
    def external_ref(self):
        return self.name

    def add_origin(self, origin):
        self._origins.add(origin)
        if self.parent is not None:
            self.parent.add_origin(origin)

    def has_origin(self, origin, strict=False):
        try:
            if strict:
                next(x for x in self._origins if x == origin)
            else:
                next(x for x in self._origins if x.startswith(origin))
        except StopIteration:
            return False
        return True

    def serialize(self):
        d = super(Context, self).serialize()
        if self.parent is None:
            if self.sense is not None:
                d['sense'] = self.sense
        return d

    def __repr__(self):
        return '<Context(%s)>' % ';'.join(self.as_list())


NullContext = Context.null()


class ContextManager(CompartmentManager):
    _entry_group = 'Compartments'  # we keep this so as to access compartment-compatible serializations
    _syn_type = Context
    _ignore_case = True

    _null_entry = NullContext

    def __init__(self, source_file=None):
        super(ContextManager, self).__init__()

        self._disregarded = set()  # this is a set of terms that

        self.new_entry('Resources', sense='source')
        self.new_entry('Emissions', sense='sink')
        self.load(source_file)

    @property
    def disregarded_terms(self):
        for t in sorted(self._disregarded):
            yield t

    def _disregard(self, comp):
        """
        The compartment's terms are added to the disregard list.  Its child compartments are "orphaned" (brutal!).
        recurse on parent.
        :param comp:
        :return:
        """
        for c in comp.subcompartments:
            c.parent = None
        for t in comp.terms:
            self._disregarded.add(t.lower())
        self.remove_entry(comp)
        if comp.parent is not None:
            self._disregard(comp.parent)

    def new_entry(self, *args, parent=None, **kwargs):
        args = tuple(filter(lambda arg: arg.lower() not in self._disregarded, args))
        if parent is not None:
            if not isinstance(parent, Compartment):
                parent = self._d[parent]
            if parent.sense is not None:
                args = tuple(_dir_mod(arg, parent.sense) for arg in args)
        return super(ContextManager, self).new_entry(*args, parent=parent, **kwargs)

    def _gen_matching_entries(self, cx):
        for t in cx.terms:
            if t in self._d:
                yield self._d[t]

    def _merge(self, existing_entry, ent):
        """
        Need to check lineage. We adopt the rule: merge is acceptable if both entries have the same top-level
        compartment or if ent has no parent.  existing entry will obviously be dominant, but any sense specification
        will overrule a 'None' sense in either existing or new.
        :param existing_entry:
        :param ent:
        :return:
        """
        if ent.sense is not None:
            existing_entry.sense = ent.sense  # this is essentially an assert w/raises InconsistentSense

        super(CompartmentManager, self)._merge(existing_entry, ent)

    def add_lineage(self, lineage, parent=None):
        """
        Create a set of local contexts, beginning with parent, that replicate those in lineage
        :param lineage:
        :param parent: [None] parent of lineage
        :return: the last created context
        """
        if parent:
            if parent not in self._l:
                raise ValueError('Parent is not known locally')
        new = None
        for lx in lineage:
            new = self.new_entry(*lx.terms, parent=parent)
            parent = new
        return new

    def find_matching_context(self, origin, cx):
        """
        The objective is to find the one context in the local hierarchy that best matches the foreign context. Then the
        context's
        best, most inclusive, most consistent way possible.  The approach is:
         - starting from cx.top() and proceeding through the lineage, find any local match
         - Once a match is found, follow subcompartments until a match is found for each successive entry.
         -

        :param origin: foreign context's native origin
        :param cx: a context, possibly from a foreign context manager
        :return: the existing context (or a newly created child context) in self
        """
        auto_name = '%s:%s' % (origin, self._tuple_to_name(cx))
        if auto_name in self:
            return self[auto_name]
        lineage = cx.seq
        current = None  # current = deepest local match
        fail = []
        while len(lineage) > 0:
            this = lineage.pop(0)  # this = active foreign match
            if current is None:
                try:
                    current = next(self._gen_matching_entries(this))
                except StopIteration:
                    continue
            else:
                try:
                    nxt = next(k for k in self._gen_matching_entries(this) if k.is_subcompartment(current))
                    current = nxt
                except StopIteration:
                    fail.append(this)

        if current is None:  # nothing found! add it from scratch
            new = self.add_lineage(cx.seq)
        else:
            if fail:
                if fail[-1] is cx:
                    new = self.add_lineage(fail, parent=current)
                else:
                    new = current
            else:
                new = current
        self.add_synonym(auto_name, new)
        return new

    def _check_subcompartment_lineage(self, current, c):
        try:
            return super(ContextManager, self)._check_subcompartment_lineage(current, c)
        except FrozenElementary:
            new = self.get(c)
            self._disregard(current)
            return new

    def __getitem__(self, item):
        if str(item).lower() in self._disregarded:
            return None
        if str(item).lower() in PROTECTED:
            raise ProtectedTerm('Use "to %s" or "from %s"' % (item, item))
        return super(ContextManager, self).__getitem__(item)
