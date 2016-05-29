from __future__ import print_function, unicode_literals

import uuid
from itertools import chain


def concatenate(*lists):
    return chain(*lists)

entity_types = ('process', 'flow', 'quantity')


class LcEntity(object):
    """
    All LC entities behave like dicts, but they all have some common properties, defined here.
    """
    _pre_fields = ['EntityType', 'Name']
    _new_fields = []
    _ref_field = []
    _post_fields = ['Comment']

    def __init__(self, entity_type, entity_uuid, **kwargs):

        if isinstance(entity_uuid, uuid.UUID):
            self._uuid = entity_uuid
        else:
            self._uuid = uuid.UUID(entity_uuid)
        self._d = dict()

        self.entity_type = entity_type
        self.reference_entity = None

        self._d['Name'] = ''
        self._d['Comment'] = ''

        self._external_ref = None

        for k, v in kwargs.items():
            self[k] = v

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

    def _validate_reference(self, ref_entity):
        if ref_entity is None:
            return True  # allow none references
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
        return [i for i in self._d.keys() if i not in self.signature_fields]

    def get_properties(self):
        """
        dict of properties and values for a given entity
        :param entity: a uuid
        :return:
        """
        d = dict()
        for i in self.properties():
            d[i] = self._d[i]
        return d


    def validate(self, ext_uuid):
        if not isinstance(ext_uuid, uuid.UUID):
            ext_uuid = uuid.UUID(ext_uuid)
        valid = True
        if self.entity_type not in entity_types:
            print('Entity type %s not valid!' % self.entity_type)
            valid = False
        if self._uuid != ext_uuid:
            print("%s: UUIDs don't match!" % self._uuid)
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
        return {
            'entityType': self.entity_type,
            'entityId': self.get_external_ref(),
            self._ref_field: self._print_ref_field(),
            'tags': self._d
        }

    def __getitem__(self, item):
        if item == self._ref_field:
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
        else:
            self._d[key] = value

    def __str__(self):
        return 'LC %s: %s' % (self.entity_type, self._d['Name'])

    def __eq__(self, other):
        """
        two entities are equal if their types, external references, and dictionaries are the same.
        internal refs do not need to be equal; reference entities do not need to be equal
        :return:
        """
        return (self._external_ref == other._external_ref and
                self._d == other._d and
                self.entity_type == other.entity_type)


class LcProcess(LcEntity):

    _ref_field = 'referenceExchange'
    _new_fields = ['SpatialScope', 'TemporalScope']

    @classmethod
    def new(cls, name, ref_exchange, **kwargs):
        """
        :param name: the name of the process
        :param ref_exchange: the reference exchange
        :return:
        """
        return cls(uuid.uuid4(), Name=name, ReferenceExchange=ref_exchange, **kwargs)

    def __init__(self, entity_uuid, **kwargs):
        super(LcProcess, self).__init__('process', entity_uuid, **kwargs)

        if 'SpatialScope' not in self._d:
            self._d['SpatialScope'] = 'GLO'
        if 'TemporalScope' not in self._d:
            self._d['TemporalScope'] = '0'

    def __str__(self):
        return '%s [%s]' % (self._d['Name'], self._d['SpatialScope'])


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

        self._ref_quantity_factor = 1

        for k in self._new_fields:
            if k not in self._d:
                self._d[k] = ''

    def set_local_unit(self, factor):
        self._ref_quantity_factor = factor

    def __str__(self):
        cas = self._d['CasNumber']
        if cas is None:
            cas = ''
        if len(cas) > 0:
            cas = ' (CAS ' + cas + ')'
        comp = ', '.join((i for i in self._d['Compartment'] if i is not None))
        return '%s%s [%s]' % (self._d['Name'], cas, comp)


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
        return cls(uuid.uuid4(), Name=name, ReferenceUnit=ref_unit, **kwargs)

    def __init__(self, entity_uuid, **kwargs):
        super(LcQuantity, self).__init__('quantity', entity_uuid, **kwargs)

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

    def __str__(self):
        return '[%s]' % self._unitstring


entity_refs = {
    'process': 'exchange',
    'flow': 'quantity',
    'quantity': 'unit'
}
