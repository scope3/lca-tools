directions = ('Input', 'Output')


class DirectionlessExchangeError(Exception):
    pass


class Exchange(object):
    """
    An exchange is an affiliation of a process, a flow, and a direction. An exchange does
    not include an exchange value- though presumably a valued exchange would be a subclass.

    An exchange may specify a quantity different from the flow's reference quantity; by default
    the reference quantity is used.
    """

    entity_type = 'exchange'

    def __init__(self, process, flow, direction, quantity=None):
        """

        :param process:
        :param flow:
        :param direction:
        :param quantity:
        :return:
        """
        assert process.entity_type == 'process', "'process' must be an LcProcess!"
        assert flow.entity_type == 'flow', "'flow' must be an LcFlow"
        assert direction in directions, "direction must be a string in (%s)" % ', '.join(directions)

        self.process = process
        self.flow = flow
        self.direction = direction
        if quantity is None:
            self.quantity = flow.reference_entity
        else:
            assert quantity.entity_type == 'quantity', "'quantity' must be an LcQuantity or None!"
            self.quantity = quantity
        self.value = None

    def __hash__(self):
        return hash((self.process.get_uuid(), self.flow.get_uuid(), self.direction))

    def __eq__(self, other):
        if other is None:
            return False
        return (self.process.get_uuid() == other.process.get_uuid() and
                self.flow.get_uuid() == other.flow.get_uuid() and
                self.direction == other.direction)

    def __str__(self):
        return '%s has %s: %s %s' % (self.process, self.direction, self.flow, self.quantity.reference_entity)

    def get_external_ref(self):
        return '%s: %s' % (self.direction, self.flow.get_uuid())

    def serialize(self, **kwargs):
        j = {
            'flow': self.flow.get_uuid(),
            'direction': self.direction,
        }
        if self in self.process.reference_entity:
            j['isReference'] = True
        return j

    @classmethod
    def signature_fields(cls):
        return ['process', 'flow', 'direction', 'quantity']


class ExchangeValue(Exchange):
    """
    An ExchangeValue is an exchange with a value
    """
    @classmethod
    def from_allocated(cls, allocated, reference):
        return cls(allocated.process, allocated.flow, allocated.direction, value=allocated[reference])

    def __init__(self, *args, value=None, **kwargs):
        super(ExchangeValue, self).__init__(*args, **kwargs)
        assert isinstance(value, float), 'ExchangeValues must be floats (or subclasses)'
        self.value = value

    def __str__(self):
        return '%6.6s: [%.3g %s] %s' % (self.direction, self.value, self.quantity.reference_entity, self.flow)

    def serialize(self, values=False):
        j = super(ExchangeValue, self).serialize()
        if values:
            j['value'] = float(self.value)
        return j


class AllocatedExchange(Exchange):
    """
    An AllocatedExchange is an alternative implementation of an ExchangeValue that behaves like an
    ordinary ExchangeValue, but also stores multiple exchange values, indexed via a dict of uuids for reference
    flows.  (It is assumed that no process features the same flow in both input and output directions AS REFERENCE
    FLOWS.)  An allocation factor can only be set for flows that are listed in the parent process's reference entity.

    If an AllocatedExchange's flow UUID is found in the value_dict, it is a reference exchange. In this case, it
    is an error if the exchange value for the reference flow is zero, or if the exchange value for any non-
    reference-flow is nonzero.  This can be checked internally without any knowledge by the parent process.

    Open question is how to serialize- whether to report only the un-allocated, only the allocated exchange values, or
    both.  Then an open task is to deserialize same.-- but that just requires serializing them as dicts
    """
    @classmethod
    def from_dict(cls, process, flow, direction, value=None):
        self = cls(process, flow, direction)
        self._value_dict.update(value)  # this will fail unless value was specified
        return self

    @classmethod
    def from_exchange(cls, exchange):
        self = cls(exchange.process, exchange.flow, exchange.direction)
        self._value = exchange.value
        return self

    def __init__(self, process, flow, direction, value=None, **kwargs):
        self._ref_flow = flow.get_uuid()  # shortcut
        self._value = value
        self._value_dict = dict()
        super(AllocatedExchange, self).__init__(process, flow, direction, **kwargs)

    def _check_ref(self):
        if self._value is not None:
            raise ValueError('Exch generic value is already set to %g (versus ref %s)' % (self._value, self._ref_flow))
        for r, v in self._value_dict.items():
            if r == self._ref_flow and v == 0:
                print('r: %s ref: %s v: %d' % (r, self._ref_flow, v))
                raise ValueError('Reference exchange value cannot be zero')
            if r != self._ref_flow and v != 0:
                print('r: %s ref: %s v: %d' % (r, self._ref_flow, v))
                raise ValueError('Reference exchange value must be zero for non-reference exchanges')

    @property
    def value(self):
        if self._ref_flow in self._value_dict:
            return self[self._ref_flow]
        if self._value is None:
            if len(self._value_dict) == 1:
                return [v for k, v in self._value_dict][0]
        return self._value

    @value.setter
    def value(self, exch_val):
        if self._ref_flow in self._value_dict:
            self._value_dict[self._ref_flow] = exch_val
        else:
            self._value = exch_val

    def keys(self):
        """
        This should be a subset of [f.get_uuid() for f in self.process.reference_entity()]
        :return:
        """
        return self._value_dict.keys()

    def values(self):
        """
        bad form to rename items() to values() ? here, values refers to exchange values- but that
        is probably weak tea to an irritated client code.
        :return:
        """
        return self._value_dict.items()

    @staticmethod
    def _normalize_key(key):
        if isinstance(key, Exchange):
            key = key.flow
        if hasattr(key, 'get_uuid'):
            key = key.get_uuid()
        return key

    def __getitem__(self, item):
        k = self._normalize_key(item)
        if k in self._value_dict:
            return self._value_dict[k]
        if k in [x.flow.get_uuid() for x in self.process.reference_entity]:
            return 0.0
        raise KeyError('Key %s is not identified as a reference exchange for the parent process' % k)

    def __setitem__(self, key, value):
        key = self._normalize_key(key)
        if key not in [x.flow.get_uuid() for x in self.process.reference_entity]:
            raise KeyError('Cannot set allocation for a non-reference flow')
        #if not isinstance(value, float):
        #    raise ValueError('Allocated exchange value must be float, found %s' % value)
        if self._ref_flow in self._value_dict:  # reference exchange
            if key == self._ref_flow:
                if value == 0:
                    raise ValueError('Reference exchange cannot be zero')
            else:
                if value != 0:
                    raise ValueError('Allocation for non-reference exchange must be zero')
        self._value_dict[key] = value
        if key == self._ref_flow:
            self._check_ref()

    def serialize(self, values=False):
        j = super(AllocatedExchange, self).serialize()
        if values:
            j['value'] = self._value_dict
        return j
