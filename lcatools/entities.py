from __future__ import print_function, unicode_literals

import uuid
import re
from itertools import chain

from lcatools.exchanges import Exchange, ExchangeValue, DuplicateExchangeError, AmbiguousReferenceError, NoAllocation
from lcatools.characterizations import Characterization
from lcatools.lcia_results import LciaResult, LciaResults


def concatenate(*lists):
    return chain(*lists)


def trim_cas(cas):
    try:
        return re.sub('^(0*)', '', cas)
    except TypeError:
        print('%s %s' % (cas, type(cas)))
        return ''


entity_types = ('process', 'flow', 'quantity', 'fragment')


class OriginExists(Exception):
    pass


class NoReferenceFound(Exception):
    pass


class MultipleReferencesFound(Exception):
    pass


class DeleteReference(Exception):
    pass


class MissingFactor(Exception):
    pass


class LcEntity(object):
    """
    All LC entities behave like dicts, but they all have some common properties, defined here.
    """
    _pre_fields = ['EntityType', 'Name']
    _new_fields = []
    _ref_field = ''
    _post_fields = ['Comment']

    def __init__(self, entity_type, entity_uuid, **kwargs):

        if isinstance(entity_uuid, uuid.UUID):
            self._uuid = entity_uuid
        else:
            self._uuid = uuid.UUID(entity_uuid)
        self._d = dict()

        self.entity_type = entity_type
        self.reference_entity = None
        self._scenarios = dict()
        self._origin = None

        self._d['Name'] = ''
        self._d['Comment'] = ''

        self._external_ref = None

        for k, v in kwargs.items():
            self[k] = v

    @property
    def origin(self):
        return self._origin

    @origin.setter
    def origin(self, value):
        if self._origin is None:
            self._origin = value
        else:
            raise OriginExists('Origin already set to %s' % self._origin)

    @classmethod
    def signature_fields(cls):
        return concatenate(cls._pre_fields, cls._new_fields,
                           [cls._ref_field] if cls._ref_field is not [] else [], cls._post_fields)

    def set_external_ref(self, ref):
        """
        Specify how the entity is referred to in the source dataset. If this is unset, the UUID is assumed
        to be used externally.
        :param ref:
        :return:
        """
        self._external_ref = ref

    def get_external_ref(self):
        return '%s' % self._uuid if self._external_ref is None else self._external_ref

    def get_signature(self):
        k = dict()
        for i in self.signature_fields():
            k[i] = self[i]
        return k

    def get_uuid(self):
        return str(self._uuid)

    def get_link(self):
        return '%s%s' % (self.origin, self.get_external_ref())

    def _validate_reference(self, ref_entity):
        if ref_entity is None:
            # raise ValueError('Null reference')
            return False  # allow none references
        if ref_entity.entity_type != entity_refs[self.entity_type]:
            raise TypeError("Type Mismatch on reference entity")
        return True

    def _set_reference(self, ref_entity):
        """
        set the entity's reference value.  Can be overridden
        :param ref_entity:
        :return:
        """
        self._validate_reference(ref_entity)
        self.reference_entity = ref_entity

    def has_property(self, prop):
        return prop in self._d

    def properties(self):
        return [i for i in self._d.keys() if i not in self.signature_fields()]

    def get_properties(self):
        """
        dict of properties and values for a given entity
        :return:
        """
        d = dict()
        for i in self.properties():
            d[i] = self._d[i]
        return d

    def update(self, d):
        self._d.update(d)

    def validate(self):
        valid = True
        if self.entity_type not in entity_types:
            print('Entity type %s not valid!' % self.entity_type)
            valid = False
        if self.reference_entity is not None:
            try:
                self._validate_reference(self.reference_entity)
            except TypeError:
                print("Reference entity type %s is wrong for %s (%s)" %
                      (self.reference_entity.entity_type,
                       self.entity_type,
                       entity_types[self.entity_type]))
                valid = False
        for i in self.signature_fields():
            try:
                self[i]
            except KeyError:
                print("Required field %s does not exist" % i)
                valid = False
        return valid

    def _print_ref_field(self):
        if self.reference_entity is None:
            return '%s' % None
        else:
            return '%s' % self.reference_entity.get_external_ref()

    def serialize(self):
        j = {
            'entityId': self.get_uuid(),
            'entityType': self.entity_type,
            'externalId': self.get_external_ref(),
            'origin': self.origin,
            self._ref_field: self._print_ref_field(),
        }
        j.update(self._d)
        return j

    def __getitem__(self, item):
        if item.lower() == self._ref_field.lower():
            return self.reference_entity
        elif item == 'EntityType':
            return self.entity_type
        else:
            # don't catch KeyErrors here-- leave that to subclasses
            return self._d[item]

    def __setitem__(self, key, value):
        if key == 'EntityType':
            raise ValueError('Entity Type cannot be changed')
        elif key.lower() == self._ref_field.lower():
            self._set_reference(value)
        elif key.lower() in ('entityid', 'entitytype', 'externalid', 'origin'):
            raise KeyError('Disallowed Keyname %s' % key)
        else:
            self._d[key] = value

    def merge(self, other):
        if not isinstance(other, LcEntity):
            raise ValueError('Incoming is not an LcEntity: %s' % other)
        elif self.entity_type != other.entity_type:
            raise ValueError('Incoming entity type %s mismatch with %s' % (other.entity_type, self.entity_type))
        elif self.get_external_ref() != other.get_external_ref():
            raise ValueError('Incoming External ref %s conflicts with existing %s' % (other.get_external_ref(),
                                                                                      self.get_external_ref()))
        else:
            # if self.origin != other.origin:
            #     print('Merging entities with differing origin: \nnew: %s\nexisting: %s'% (other.origin, self.origin))
            for k in other.keys():
                if k not in self.keys():
                    print('Merge: Adding key %s: %s' % (k, other[k]))
                    self[k] = other[k]

    def keys(self):
        return self._d.keys()

    def show(self):
        print('%s Entity (ref %s)' % (self.entity_type.title(), self.get_external_ref()))
        fix = ['Name', 'Comment']
        postfix = set(self._d.keys()).difference(fix)
        ml = len(max(self._d.keys(), key=len))
        for k in fix:
            print('%*s: %s' % (ml, k, self._d[k]))
        for k in postfix:
            print('%*s: %s' % (ml, k, self._d[k]))

    def __str__(self):
        return 'LC %s: %s' % (self.entity_type, self._d['Name'])

    def __hash__(self):
        return hash(self._uuid)

    def __eq__(self, other):
        """
        two entities are equal if their types, origins, and external references are the same.
        internal refs do not need to be equal; reference entities do not need to be equal
        :return:
        """
        if other is None:
            return False
        return (self.get_external_ref() == other.get_external_ref() and
                self.origin == other.origin and
                self.entity_type == other.entity_type)


class LcProcess(LcEntity):

    _ref_field = 'referenceExchange'
    _new_fields = ['SpatialScope', 'TemporalScope']

    @classmethod
    def new(cls, name, **kwargs):
        """
        :param name: the name of the process
        :return:
        """
        return cls(uuid.uuid4(), Name=name, **kwargs)

    def __init__(self, entity_uuid, **kwargs):
        self._exchanges = dict()
        super(LcProcess, self).__init__('process', entity_uuid, **kwargs)
        if self.reference_entity is not None:
            raise AttributeError('How could the reference entity not be None?')
        self.reference_entity = set()  # it is not possible to specify a valid reference_entity on init

        if 'SpatialScope' not in self._d:
            self._d['SpatialScope'] = 'GLO'
        if 'TemporalScope' not in self._d:
            self._d['TemporalScope'] = '0'

    def __str__(self):
        return '%s [%s]' % (self._d['Name'], self._d['SpatialScope'])

    def add_scenario(self, scenario, reference):
        """
        Here's how scenarios work:
        a scenario acts equivalently to an alternative reference flow in an allocation exchange.
        When a user wants to define a new scenario parameter- first the process needs to know it is parameterized
        within that scenario- and what reference to use for un-parameterized exchanges. that's what add_scenario is for.
        Then, the user can parameterize a specific exchange-> the exchange gets upgraded to an AllocatedExchange
        if it is not already so, the scenario id is used as the reference flow, and the param value is installed
        as the exchange value.
        When a user makes an exchange query, they specify a reference flow (or no reference).  If the reference flow
        shows up in the list of scenarios, then the internal exchange answering mechanism switches gears:
         - if the scenario is a reference in the exchange, it uses that;
         - otherwise it uses the reference pointed to by the process's scenarios dict (set here)

        implication is that an allocated exchange should be earlier in inheritance than an exchange value- but the
        current workaround is satisfactory for ff params and pf params excluding dissipation (dissipation
        would inherit from exchangevalue). LCIA params (as
        previously observed) should / could be new quantities- flow property params in general need a reworking
         of the current [location] spec- which is the same as the param interface- but not today.

         reference: fragment traversal- TODO
        :param scenario:
        :param reference:
        :return:
        """
        if reference in self.reference_entity:
            self._scenarios[scenario] = reference

    def _validate_reference(self, ref_set):
        for x in ref_set:
            if not super(LcProcess, self)._validate_reference(x):
                return False
        return True

    def _print_ref_field(self):
        return 'see exchanges'

    def _set_reference(self, ref_entity):
        """
        is it a problem that there's no way to un-set reference exchanges? my feeling is no, at least at present.
        :param ref_entity:
        :return:
        """
        self._validate_reference({ref_entity})

        self.reference_entity.add(ref_entity)

    def find_reference_by_string(self, term, strict=False):
        """
        Select a reference based on a search term--- check against flow.  test get_uuid().startswith, or ['Name'].find()
        If multiple results found- if strict, return None; if strict=False, return first
        :param term:
        :param strict: [False] raise error if ambiguous search term; otherwise return first
        :return: the exchange entity
        """
        hits = [None] * len(self.reference_entity)
        for i, e in enumerate(self.reference_entity):
            if e.flow.get_uuid().startswith(term):
                hits[i] = e
            elif e.flow['Name'].lower().find(term.lower()) >= 0:
                hits[i] = e
        hits = list(filter(None, hits))
        if strict:
            if len(hits) > 1:
                raise MultipleReferencesFound('process:%s key: %s' % (self, term))
        if len(hits) == 0:
            raise NoReferenceFound('process:%s key: %s' % (self, term))
        return hits[0]

    def inventory(self, reference=None):
        out = []
        it = self.exchanges(reference)
        if reference is None:
            print('%s' % self)
        else:
            print('Reference: %s' % ExchangeValue.from_allocated(reference, reference))  # get in unit terms
        for i in it:
            print('%2d %s' % (len(out), i))
            out.append(i)
        return out

    def exchange(self, flow, direction=None):
        if isinstance(flow, LcFlow):
            for x in self._exchanges.values():
                if x.flow == flow:
                    if direction is None:
                        yield x
                    else:
                        if x.direction == direction:
                            yield x
        elif flow in self._scenarios:
            for x in self._exchanges.values():
                if x.flow == self._scenarios[flow]:
                    yield x
        else:
            raise TypeError('LcProcess.exchange input %s %s' % (flow, type(flow)))

    def has_exchange(self, flow, direction=None):
        try:
            x = next(self.exchange(flow, direction=direction))
        except StopIteration:
            return False
        return True

    def exchanges(self, reference=None, scenario=None, strict=False):
        """
        generate a process's exchanges.  If no reference is supplied, generate unallocated exchanges, including all
        reference exchanges.  If a reference is supplied, generate ExchangeValues as allocated to that reference flow,
        and exclude reference exchanges.  Reference must be a flow or exchange found in the process's reference entity.

        Replaces allocated_exchange(reference), which is deprecated.
        this is going to be part of a major upcoming refactor, since ExchangeValue and AllocatedExchange are going to
        be merged.
        :param reference:
        :param scenario: not fully implemented
        :param strict: [False] whether to use strict flow name matching [default- first regex match]
        :return:
        """
        if reference is not None:
            reference = self.find_reference(reference, strict=strict)
        for i in sorted(self._exchanges.values(), key=lambda x: x.direction):
            if reference is None:
                yield i
            else:
                if i in self.reference_entity:
                    pass
                else:
                    if scenario is not None:
                        yield ExchangeValue.from_scenario(i, scenario, reference)
                    else:
                        # this pushes the problem up to ExchangeValue
                        yield ExchangeValue.from_allocated(i, reference)

    def find_reference(self, reference, strict=False):
        """
        returns an exchange. NOTE: this has been refactored.
        :param reference:
        :param strict:
        :return:
        """
        if reference is None:
            if len(self.reference_entity) > 1:
                raise NoReferenceFound('Must specify reference!')
            ref = next(x for x in self.reference_entity)
        elif isinstance(reference, str):
            x = self.find_reference_by_string(reference, strict=strict)
            ref = x
        elif isinstance(reference, LcFlow):
            try:
                ref = next(rf for rf in self.reference_entity if rf.flow == reference)
            except StopIteration:
                raise NoReferenceFound('No reference exchange found with flow %s' % reference)
        elif isinstance(reference, Exchange):
            if reference in self.reference_entity:
                return reference
            else:
                raise NoReferenceFound('Exchange is not a reference exchange %s' % reference)
        else:
            raise NoReferenceFound('Unintelligible reference %s' % reference)
        return ref

    def add_reference(self, flow, dirn):
        rx = Exchange(self, flow, dirn)
        self._set_reference(rx)
        return rx

    def remove_reference(self, reference):
        if reference in self.reference_entity:
            self.remove_allocation(reference)
            self.reference_entity.remove(reference)

    def references(self, flow=None):
        for rf in self.reference_entity:
            if flow is None:
                yield self._exchanges[rf]
            else:
                if rf.flow == flow:
                    yield self._exchanges[rf]

    def reference(self, flow=None):
        ref = [rf for rf in self.references(flow)]
        if len(ref) == 0:
            raise NoReferenceFound
        elif len(ref) > 1:
            raise AmbiguousReferenceError('Multiple matching references found')
        return ref[0]

    def allocate_by_quantity(self, quantity):
        """
        Apply allocation factors to all non-reference exchanges, determined by the quantity specified.  For each
        reference exchange, computes the magnitude of the quantity output from the unallocated process. Reference flows
        lacking characterization in that quantity will receive zero allocation.

        Each magnitude is the allocation numerator for that reference, and the sum of the magnitudes is the allocation
        denominator. For each reference the allocated exchanges are normalized by the magnitude of the reference
        exchange's reference quantity.  This means that the normalizing allocation factor is actually the reference
        exchange's characterization divided by the total.
        :param quantity: an LcQuantity
        :return:
        """
        exchs = dict()
        mags = dict()
        for rf in self.reference_entity:
            exchs[rf.flow] = self._exchanges[rf].value
            mags[rf.flow] = exchs[rf.flow] * rf.flow.cf(quantity)

        total = sum([v for v in mags.values()])

        for rf in self.reference_entity:
            alloc_factor = rf.flow.cf(quantity) / total  # qty magnitude divided by total, divided by exch magnitude
            for x in self.exchanges():
                if x not in self.reference_entity:
                    x[rf] = x.value * alloc_factor
        self['AllocatedByQuantity'] = quantity

    def is_allocated(self, reference):
        """
        Tests whether a process's exchanges contain allocation factors for a given reference.
        :param reference:
        :return: True - allocations exist; False - no allocations exist; raise MissingFactor - some allocations exist
        """
        missing_allocations = []
        has_allocation = []
        for x in self._exchanges.values():
            if x in self.reference_entity:
                continue
            try:
                v = x[reference]
                has_allocation.append(v)
            except NoAllocation:
                missing_allocations.append(x)
        if len(has_allocation) * len(missing_allocations) == 0:
            if len(has_allocation) == 0:
                return False
            return True
        for x in missing_allocations:
            print('%s' % x)
            raise MissingFactor('Missing allocation factors for above exchanges')

    def remove_allocation(self, reference):
        for x in self._exchanges.values():
            x.remove_allocation(reference)

    def add_exchange(self, flow, dirn, reference=None, value=None, add_dups=False, **kwargs):
        """
        This is used to create Exchanges and ExchangeValues and AllocatedExchanges.

        If the flow+dirn is already in the exchange set:
            if no reference is specified and/or no value is specified- nothing to do
            otherwise (if reference and value are specified):
                upgrade the exchange to an allocatedExchange and add the new reference exch val
        otherwise:
            if reference is specified, create an AllocatedExchange
            otherwise create an Exchange / ExchangeValue

        :param flow:
        :param dirn:
        :param reference:
        :param value:
        :param add_dups: (False) set to true to handle "duplicate exchange" errors by cumulating their values
        :return:
        """
        _x = Exchange(self, flow, dirn, **kwargs)
        if _x in self._exchanges:
            if value is None or value == 0:
                return None
            e = self._exchanges[_x]
            if reference is None:
                if isinstance(value, dict):
                    e.update(value)
                else:
                    try:
                        e.value = value  # this will catch already-set errors
                    except DuplicateExchangeError:
                        if add_dups:
                            e.add_to_value(value)
                        else:
                            print('Duplicate exchange in process %s:\n%s' % (self.get_uuid(), e))
                            raise
                return e

            else:
                try:
                    e[reference] = value  # this will catch already-set errors
                except DuplicateExchangeError:
                    if add_dups:
                        e.add_to_value(value, reference=reference)
                    else:
                        print('Duplicate exchange in process %s:\n%s' % (self.get_uuid(), e))
                        raise
                except ValueError:
                    print('Error adding [%s] = %10.3g for exchange\n%s\nto process\n%s' % (
                        reference.flow.get_uuid(), value, e, self.get_external_ref()))
                    raise

                return e

        else:
            if value is None or value == 0:
                e = _x
            elif isinstance(value, float):
                if reference is None:
                    e = ExchangeValue(self, flow, dirn, value=value, **kwargs)
                else:
                    if reference not in self.reference_entity:
                        raise KeyError('Specified reference is not registered with process: %s' % reference)
                    e = ExchangeValue(self, flow, dirn, value=None, **kwargs)
                    e[reference] = value

            elif isinstance(value, dict):
                e = ExchangeValue.from_dict(self, flow, dirn, value_dict=value, **kwargs)
            else:
                raise TypeError('Unhandled value type %s' % type(value))
            if e in self._exchanges:
                raise KeyError('Exchange already present')
            # self._exchanges.add(e)
            self._exchanges[e] = e
            return e

    def lcias(self, quantities, **kwargs):
        results = LciaResults(entity=self)
        for q in quantities:
            results[q.get_uuid()] = self.lcia(q, **kwargs)
        return results

    def lcia(self, quantity, ref_flow=None, scenario=None, flowdb=None):
        result = LciaResult(quantity, scenario)
        result.add_component(self.get_uuid(), entity=self)
        for ex in self.exchanges(ref_flow, scenario=scenario):
            if not ex.flow.has_characterization(quantity):
                if flowdb is not None:
                    if quantity in flowdb.known_quantities():
                        factor = flowdb.lookup_single_cf(ex.flow, quantity, self['SpatialScope'])
                        if factor is None:
                            ex.flow.add_characterization(quantity)
                        else:
                            ex.flow.add_characterization(factor)
            factor = ex.flow.factor(quantity)
            result.add_score(self.get_uuid(), ex, factor, self['SpatialScope'])
        return result

    def merge(self, other):
        raise NotImplemented('This should be done via fragment construction + aggregation')

    def serialize(self, exchanges=False, **kwargs):
        j = super(LcProcess, self).serialize()
        j.pop(self._ref_field)  # reference reported in exchanges
        if exchanges:
            # if exchanges is true, report all exchanges
            j['exchanges'] = sorted([x.serialize(**kwargs) for x in self._exchanges.values()],
                                    key=lambda x: (x['direction'], x['flow']))
        else:
            # if exchanges is false, only report reference exchanges
            j['exchanges'] = sorted([x.serialize(**kwargs) for x in self._exchanges.values()
                                     if x in self.reference_entity],
                                    key=lambda x: (x['direction'], x['flow']))
        return j


class LcFlow(LcEntity):

    _ref_field = 'referenceQuantity'
    _new_fields = ['CasNumber', 'Compartment']

    @classmethod
    def new(cls, name, ref_qty, **kwargs):
        """
        :param name: the name of the flow
        :param ref_qty: the reference quantity
        :return:
        """
        return cls(uuid.uuid4(), Name=name, ReferenceQuantity=ref_qty, **kwargs)

    def __init__(self, entity_uuid, **kwargs):
        super(LcFlow, self).__init__('flow', entity_uuid, **kwargs)

        self._characterizations = dict()

        self._ref_quantity_factor = 1.0

        for k in self._new_fields:
            if k not in self._d:
                self._d[k] = ''

        if self['CasNumber'] is None:
            self['CasNumber'] = ''

        if self.reference_entity is not None:
            if self.reference_entity.get_uuid() not in self._characterizations.keys():
                self.add_characterization(self.reference_entity, reference=True, value=self._ref_quantity_factor)

    def _set_reference(self, ref_entity):
        if self.reference_entity is not None:
            if self.reference_entity.get_uuid() == ref_entity.get_uuid():
                return
            # need to do a conversion
            print('Changing reference quantity for flow %s' % self)
            print('reference >>%s<<' % self.reference_entity)
            print('refer.new >>%s<<' % ref_entity)
            inc = self.cf(ref_entity)  # divide by 0 if not known
            if inc is None or inc == 0:
                raise MissingFactor('Flow %s missing factor for reference quantity %s' % (self, ref_entity))
            adj = 1.0 / inc
            for v in self._characterizations.values():
                v.scale(adj)
        super(LcFlow, self)._set_reference(ref_entity)

    def unit(self):
        return self.reference_entity.unit()

    def set_local_unit(self, factor):
        self._ref_quantity_factor = factor

    def match(self, other):
        return (self.get_uuid() == other.get_uuid() or
                self['Name'].lower() == other['Name'].lower() or
                (trim_cas(self['CasNumber']) == trim_cas(other['CasNumber']) and len(self['CasNumber']) > 4) or
                self.get_external_ref() == other.get_external_ref())

    def __str__(self):
        cas = self._d['CasNumber']
        if cas is None:
            cas = ''
        if len(cas) > 0:
            cas = ' (CAS ' + cas + ')'
        comp = self._d['Compartment'][-1]  # '', '.join((i for i in self._d['Compartment'] if i is not None))
        return '%s%s [%s]' % (self._d['Name'], cas, comp)

    def profile(self):
        print('%s' % self)
        out = []
        for cf in self._characterizations.values():
            print('%2d %s' % (len(out), cf.q_view()))
            out.append(cf)
        return out

    def add_characterization(self, quantity, reference=False, value=None, **kwargs):
        if isinstance(quantity, Characterization):
            for l in quantity.locations():
                self.add_characterization(quantity.quantity, reference=reference,
                                          value=quantity[l], location=l)
            return
        if not isinstance(quantity, LcQuantity):  # assume it's a CatalogRef
            quantity = quantity.entity()
        if reference:
            if value is None:
                value = 1.0
            self.set_local_unit(value)
            self._set_reference(quantity)

        q = quantity.get_uuid()
        c = Characterization(self, quantity)
        if q in self._characterizations.keys():
            if value is None:
                return
            c = self._characterizations[q]
        else:
            self._characterizations[q] = c
        if value is not None:
            if isinstance(value, dict):
                c.update_values(**value)
            else:
                c.add_value(value=value, **kwargs)

    def has_characterization(self, quantity, location='GLO'):
        if quantity.get_uuid() in self._characterizations.keys():
            if location == 'GLO':
                return True
            if location in self._characterizations[quantity.get_uuid()].locations():
                return True
        return False

    def del_characterization(self, quantity):
        if quantity is self.reference_entity:
            raise DeleteReference('Cannot delete reference quantity')
        self._characterizations.pop(quantity.get_uuid())

    def characterizations(self):
        for i in self._characterizations.values():
            yield i

    def factor(self, quantity):
        if quantity.get_uuid() in self._characterizations:
            return self._characterizations[quantity.get_uuid()]
        return Characterization(self, quantity)

    def cf(self, quantity, location='GLO'):
        if quantity.get_uuid() in self._characterizations:
            try:
                return self._characterizations[quantity.get_uuid()][location]
            except KeyError:
                return self._characterizations[quantity.get_uuid()].value
        return 0.0

    def convert(self, val, to=None, fr=None, location='GLO'):
        """
        converts the value (in
        :param val:
        :param to: to quantity
        :param fr: from quantity
        :param location: cfs are localized to unrestricted strings babee
        the flow's reference quantity is used if either is unspecified
        :return: value * self.char(to)[loc] / self.char(fr)[loc]
        """
        out = self.cf(to or self.reference_entity, location=location)
        inn = self.cf(fr or self.reference_entity, location=location)
        return val * out / inn

    def merge(self, other):
        super(LcFlow, self).merge(other)
        for k in other._characterizations.keys():
            if k not in self._characterizations:
                print('Merge: Adding characterization %s' % k)
                self.add_characterization(other._characterizations[k])

    def serialize(self, characterizations=False, **kwargs):
        j = super(LcFlow, self).serialize()
        j.pop(self._ref_field)  # reference reported in characterizations
        if characterizations:
            j['characterizations'] = sorted([x.serialize(**kwargs) for x in self._characterizations.values()],
                                            key=lambda x: x['quantity'])
        else:
            j['characterizations'] = [x.serialize(**kwargs) for x in self._characterizations.values()
                                      if x.quantity == self.reference_entity]

        return j


class LcQuantity(LcEntity):

    _ref_field = 'referenceUnit'
    _new_fields = []

    @classmethod
    def new(cls, name, ref_unit, **kwargs):
        """
        :param name: the name of the quantity
        :param ref_unit: the string representation of the reference unit for the quantity
        :return:
        """
        return cls(uuid.uuid4(), Name=name, ReferenceUnit=LcUnit(ref_unit), **kwargs)

    def __init__(self, entity_uuid, **kwargs):
        super(LcQuantity, self).__init__('quantity', entity_uuid, **kwargs)

    def unit(self):
        return self.reference_entity.unitstring()

    def is_lcia_method(self):
        return 'Indicator' in self.keys()

    def convert(self, from_unit, to=None):
        """
        Perform unit conversion within a quantity, using a 'UnitConversion' table stored in the object properties.
        For instance, if the quantity name was 'mass' and the reference unit was 'kg', then
        quantity.convert('lb') would[should] return 0.4536...
        quantity.convert('lb', to='ton') should return 0.0005

        This function requires that the quantity have a 'UnitConversion' property that works as a dict, with
        the unit names being keys. The requirement is that the values for every key all correspond to the same
        quantity.  For instance, if the quantity was mass, then the following would be equivalent:

        quantity['UnitConversion'] = { 'kg': 1, 'lb': 2.204622, 'ton': 0.0011023, 't': 0.001 }
        quantity['UnitConversion'] = { 'kg': 907.2, 'lb': 2000.0, 'ton': 1, 't': 0.9072 }

        If the quantity's reference unit is missing from the dict, it is assumed to be 1 implicitly.

        :param from_unit:
        :param to: unit to convert to (default is the reference unit)
        :return: a float indicating how many to_units there are in one from_unit
        """
        try:
            uc_table = self._d['UnitConversion']
        except KeyError:
            print('No unit conversion table found.')
            return None

        try:
            inbound = uc_table[from_unit]
        except KeyError:
            print('Inbound unit %s not found in unit conversion table.' % from_unit)
            return None

        if to is None:
            to = self.reference_entity

        try:
            outbound = uc_table[to]
        except KeyError:
            if to == self.reference_entity:
                outbound = 1.0
            else:
                print('Outbound unit %s not found in unit conversion table.' % to)
                return None

        return outbound / inbound

    def reset_unitstring(self, ustring):
        self.reference_entity.reset_unitstring(ustring)

    def _name(self):
        return '%s [%s]' % (self._d['Name'], self.reference_entity.unitstring())

    def __str__(self):
        if self.is_lcia_method():
            return '%s [LCIA]' % self._name()
        return '%s' % self._name()


class LcUnit(object):
    """
    Dummy class to store a reference to a unit definition
    Design decision: even though ILCD unitgroups have assigned UUIDs, we are not maintaining unitgroups
    """
    entity_type = 'unit'

    def __init__(self, unitstring, unit_uuid=None):
        if unit_uuid is not None:
            self._uuid = uuid.UUID(unit_uuid)
        else:
            self._uuid = None
        self._unitstring = unitstring
        self._external_ref = None

    def set_external_ref(self, external_ref):
        self._external_ref = external_ref

    def get_external_ref(self):
        return '%s' % self._unitstring if self._external_ref is None else self._external_ref

    def unitstring(self):
        return self._unitstring

    def get_uuid(self):
        return self._unitstring  # needed for upward compat

    def __str__(self):
        return '[%s]' % self._unitstring

    def reset_unitstring(self, ustring):
        self._external_ref = ustring
        self._unitstring = ustring


entity_refs = {
    'process': 'exchange',
    'flow': 'quantity',
    'quantity': 'unit',
    'fragment': 'fragment'
}
