"""
This object replaces the LciaResult types spelled out in Antelope-- instead, it serializes to an LCIA result directly.

"""
from lcatools.exchanges import ExchangeValue, DissipationExchange
from lcatools.characterizations import Characterization
# from lcatools.interfaces import to_uuid


from collections import defaultdict


'''
def get_entity_uuid(item):
    if to_uuid(item) is not None:
        return item
    if hasattr(item, 'get_uuid'):
        return item.get_uuid()
    raise TypeError('Don\'t know how to get ID from %s' % type(item))
'''


class InconsistentQuantity(Exception):
    pass


class InconsistentScenario(Exception):
    pass


class DuplicateResult(Exception):
    pass


def number(val):
    try:
        return '%10.3g' % val
    except TypeError:
        return '%10.10s' % '----'


class DetailedLciaResult(object):
    """
    Contains exchange, factor, result
    """
    def __init__(self, lc_result, exchange, factor, location):
        self.exchange = exchange
        self.factor = factor
        self._dirn_mod = None
        if location in factor.locations():
            self.location = location
        else:
            self.location = 'GLO'
        self._lc = lc_result

    @property
    def _dirn_adjust(self):
        """
        Memoized direction correction for "Outputs" "from ground" and "Inputs" "to environment"
        :return:
        """
        if self._dirn_mod is None:
            natural_direction = self.factor.natural_direction
            if natural_direction is None or natural_direction is False:
                self._dirn_mod = 1.0
            elif self.exchange.direction == natural_direction:
                self._dirn_mod = 1.0
            else:
                self._dirn_mod = -1.0
        return self._dirn_mod

    @property
    def flow(self):
        return self.exchange.flow.get_uuid()

    @property
    def direction(self):
        return self.exchange.direction

    @property
    def content(self):
        if isinstance(self.exchange, DissipationExchange):
            return self.exchange.content()
        return None

    @property
    def _value(self):
        if self.exchange.value is None:
            return 0.0
        return self.exchange.value * self._lc.scale * self._dirn_adjust

    @property
    def result(self):
        if self.factor.is_null:
            return 0.0
        return self._value * (self.factor[self.location] or 0.0)

    def __hash__(self):
        return hash((self.exchange.process.get_uuid(), self.exchange.direction, self.factor.flow.get_uuid()))

    def __eq__(self, other):
        if not isinstance(other, DetailedLciaResult):
            return False
        return (self.exchange.process.get_uuid() == other.exchange.process.get_uuid() and
                self.factor.flow.get_uuid() == other.factor.flow.get_uuid())

    def __str__(self):
        if self._dirn_adjust == -1:
            dirn_mod = '*'
        else:
            dirn_mod = ' '
        return '%s%s x %-s  = %-s [%s] %s' % (dirn_mod,
                                              number(self._value), number(self.factor[self.location]),
                                              number(self.result),
                                              self.location,
                                              self.factor.flow)


class SummaryLciaResult(object):
    """
    like a DetailedLciaResult except omitting the exchange and factor information.  This makes them totally static.
    """
    def __init__(self, lc_result, entity, node_weight, unit_score):
        """
        :param lc_result: who "owns" you. scale report by their scale.
        entity_id must either have get_uuid() or be hashable
        :param entity: a hashable identifier
        :param node_weight: stand-in for exchange value
        :param unit_score: stand-in for factor value
        """
        self.entity = entity
        self.node_weight = node_weight
        self.unit_score = unit_score
        self._scale = lc_result.scale  # property

    @property
    def result(self):
        return self.node_weight * self.unit_score * self._scale

    def __hash__(self):
        try:
            h = self.entity.get_uuid()
        except AttributeError:
            h = self.entity
        return hash(h)

    def __eq__(self, other):
        if not isinstance(other, SummaryLciaResult):
            return False
        return self.entity == other.entity

    def __str__(self):
        return '%s x %-s = %-s %s' % (number(self.node_weight), number(self.unit_score),
                                      number(self.result),
                                      self.entity)


class AggregateLciaScore(object):
    """
    contains an entityId which should be either a process or a fragment (fragment stages show up as fragments??)
    The Aggregate score is constructed either from individual LCIA Details (exchange value x characterization factor)
    or from summary results
    """
    def __init__(self, entity):
        self.entity = entity
        self.LciaDetails = set()

    @property
    def cumulative_result(self):
        if len(self.LciaDetails) == 0:
            return 0.0
        return sum([i.result for i in self.LciaDetails])

    def _augment_entity_contents(self, other):
        """
        when duplicate fragmentflows are aggregated, their node weights and magnitudes should be added together
        :return:
        """
        self.entity = self.entity + other

    def add_detailed_result(self, lc_result, exchange, factor, location):
        d = DetailedLciaResult(lc_result, exchange, factor, location)
        if d in self.LciaDetails:
            if factor[location] != 0:
                other = next(k for k in self.LciaDetails if k == d)
                if other.factor[location] != factor[location]:
                    raise DuplicateResult('exchange: %s\n  factor: %s\nlocation: %s\nconflicts with %s' %
                                          (exchange, factor, location, other.factor))
                else:
                    self.LciaDetails.remove(other)
                    self.add_summary_result(lc_result, other.exchange.process,
                                            other.exchange.value + exchange.value, factor[location])
                    self._augment_entity_contents(d)
                    return
            else:
                # do nothing
                return
        self.LciaDetails.add(d)

    def add_summary_result(self, lc_result, entity, node_weight, unit_score):
        d = SummaryLciaResult(lc_result, entity, node_weight, unit_score)
        if d in self.LciaDetails:
            other = next(k for k in self.LciaDetails if k == d)
            if other.unit_score != d.unit_score:
                raise DuplicateResult()
            else:
                other.node_weight += node_weight
                self._augment_entity_contents(other)
                return
        self.LciaDetails.add(d)

    def show(self, **kwargs):
        self.show_detailed_result(**kwargs)

    def details(self):
        """
        generator of nonzero detailed results
        :return:
        """
        for d in self.LciaDetails:
            if d.result != 0:
                yield d

    def show_detailed_result(self, key=lambda x: x.result, show_all=False):
        for d in sorted(self.LciaDetails, key=key, reverse=True):
            if d.result != 0 or show_all:
                print('%s' % d)
        print('=' * 60)
        print('             Total score: %g ' % self.cumulative_result)

    def __str__(self):
        return '%s  %s' % (number(self.cumulative_result), self.entity)


def show_lcia(lcia_results):
    """
    Takes in a dict of uuids to lcia results, and summarizes them in a neat table
    :param lcia_results:
    :return:
    """
    print('LCIA Results\n%s' % ('-' * 60))
    for r in lcia_results.values():
        print('%10.5g %s' % (r.total(), r.quantity))


class LciaResult(object):
    """
    An LCIA result object contains a collection of LCIA results for a related set of entities, called components.  Each
     component is an AggregateLciaScore, which itself is a collection of either detailed LCIA results or summary scores.

    Each component which is a FragmentFlow represents a specific traversal scenario and is thus static.

    Each component which is a process will contain actual exchanges and factors, which are scenario-sensitive, and
     so is (theoretically) dynamic. This is not yet useful in practice.  LCIA Results are in sharp need of testing /
     refactoring.
    """
    @classmethod
    def from_cfs(cls, fragment, cfs, scenario=None, location=None):
        """
        for foreground-terminated elementary flows
        returns a dict of LciaResults
        :param fragment:
        :param cfs: a dict of q-uuid to cf sets???
        :param scenario:
        :param location:
        :return:
        """
        results = LciaResults(fragment)
        exch = ExchangeValue(fragment, fragment.flow, fragment.direction, value=1.0)
        for q, cf in cfs.items():
            qu = q.get_uuid()
            results[qu] = cls(q, scenario=scenario)
            if isinstance(cf, Characterization):
                results[qu].add_component(fragment.get_uuid(), entity=fragment)
                results[qu].add_score(fragment.get_uuid(), exch, cf, location)

        return results

    def __init__(self, quantity, scenario=None, private=False, scale=1.0):
        """
        If private, the LciaResult will not return any unaggregated results
        :param quantity:
        :param scenario:
        :param private:
        """
        self.quantity = quantity
        self.scenario = scenario
        self._scale = scale
        self._LciaScores = dict()
        self._private = private

    @property
    def scale(self):
        return self._scale

    def set_scale(self, scale):
        """
        why is this a function?
        """
        self._scale = scale

    def _match_key(self, item):
        """
        whaaaaaaaaaat is going on here
        :param item:
        :return:
        """
        if item in self._LciaScores:
            yield self._LciaScores[item]
        else:
            for k, v in self._LciaScores.items():
                if item == v.entity:
                    yield v
                # elif str(v.entity).startswith(str(item)):
                #     yield v
                # elif str(k).startswith(str(item)):
                #     yield v
        yield AggregateLciaScore(None)

    def __getitem__(self, item):
        return next(self._match_key(item))

    '''
    def __getitem__(self, item):
        if isinstance(item, int):
            return
    '''

    def aggregate(self, key=lambda x: x.fragment['StageName']):
        """
        returns a new LciaResult object in which the components of the original LciaResult object are aggregated
        according to a key.  The key is a lambda expression that is applied to each AggregateLciaScore component's
        entity property (components where the lambda fails will all be grouped together).

        The special key '*' will aggregate all components together.

        :param key: default: lambda x: x.fragment['StageName'] -- assuming the payload is a FragmentFlow
        :return:
        """
        agg_result = LciaResult(self.quantity, scenario=self.scenario, private=self._private, scale=self._scale)
        if key == '*':
            key = lambda x: 'result'
        for v in self._LciaScores.values():
            keystring = 'other'
            try:
                keystring = key(v.entity)
            finally:
                agg_result.add_summary(keystring, v.entity, 1.0, v.cumulative_result)
        return agg_result

    def show_agg(self, **kwargs):
        self.aggregate(**kwargs).show_components()  # deliberately don't return anything- or should return grouped?

    @property
    def is_private(self):
        return self._private

    def total(self):
        return sum([i.cumulative_result for i in self._LciaScores.values()])

    def range(self):
        return sum([abs(i.cumulative_result) for i in self._LciaScores.values()])

    def add_component(self, key, entity=None):
        if entity is None:
            entity = key
        if key not in self._LciaScores.keys():
            self._LciaScores[key] = AggregateLciaScore(entity)

    def add_score(self, key, exchange, factor, location):
        if factor.quantity.get_uuid() != self.quantity.get_uuid():
            raise InconsistentQuantity('%s\nfactor.quantity: %s\nself.quantity: %s' % (factor,
                                                                                       factor.quantity.get_uuid(),
                                                                                       self.quantity.get_uuid()))
        if key not in self._LciaScores.keys():
            self.add_component(key)
        self._LciaScores[key].add_detailed_result(self, exchange, factor, location)

    def add_summary(self, key, entity, node_weight, unit_score):
        if key not in self._LciaScores.keys():
            self.add_component(key)
        self._LciaScores[key].add_summary_result(self, entity, node_weight, unit_score)

    def keys(self):
        if self._private:
            return [None]
        return self._LciaScores.keys()

    def components(self):
        if self._private:
            return [None]
        return [k.entity for k in self._LciaScores.values()]

    def component(self, key):
        if self._private:
            return self
        return self._LciaScores[key]

    def _header(self):
        print('%s %s' % (self.quantity, self.quantity.reference_entity.unitstring))
        print('-' * 60)
        if self._scale != 1.0:
            print('%60s: %10.4g' % ('scale', self._scale))

    def show(self):
        self._header()
        print('%s' % self)

    def show_components(self):
        self._header()
        if not self._private:
            for v in sorted(self._LciaScores.values(), key=lambda x: x.cumulative_result, reverse=True):
                print('%s' % v)
            print('==========')
        print('%s' % self)

    def show_details(self, key=None, **kwargs):
        self._header()
        if not self._private:
            if key is None:
                for e in self._LciaScores.keys():
                    self._LciaScores[e].show_detailed_result(**kwargs)
            else:
                self._LciaScores[key].show_detailed_result(**kwargs)
        print('%s' % self)

    def __add__(self, other):
        if self.quantity != other.quantity:
            raise InconsistentQuantity
        if self.scenario != other.scenario:
            raise InconsistentScenario
        s = LciaResult(self.quantity, self.scenario)
        for k, v in self._LciaScores.items():
            s._LciaScores[k] = v
        for k, v in other._LciaScores.items():
            s._LciaScores[k] = v
        return s

    def __str__(self):
        return '%s %s' % (number(self.total()), self.quantity)

    # charts
    def contrib_query(self, stages=None):
        """
        returns a list of scores
        :param stages: [None] a list of stages to query, or None to return all components.
         Specify '*' to return a 1-item list containing just the total.

        :return:
        """
        if stages == '*':
            return [self.total()]
        elif stages is None:
            stages = self.components()

        data = []
        for c in stages:
            try:
                data.append(self[c].cumulative_result)
            except (KeyError, StopIteration):
                data.append(0)
        return data


class LciaResults(dict):
    """
    A dict of LciaResult objects, with some useful attachments.  The dict gets added to in the normal way, but
    also keeps track of the keys added in sequence, so that they can be retrieved by numerical index.

    The LciaResults object keys should be quantity UUIDs


    """
    def __init__(self, entity, *args, **kwargs):
        super(LciaResults, self).__init__(*args, **kwargs)
        self.entity = entity
        self._scale = 1.0
        self._indices = []

    def __getitem__(self, item):
        """
        __getitem__ can either be used as a numerical index
        :param item:
        :return:
        """
        try:
            int(item)
            return super(LciaResults, self).__getitem__(self._indices[item])
        except (ValueError, TypeError):
            try:
                return super(LciaResults, self).__getitem__(next(k for k in self.keys() if k.startswith(item)))
            except StopIteration:
                return LciaResult(None)  #

    def __setitem__(self, key, value):
        assert isinstance(value, LciaResult)
        value.set_scale(self._scale)
        super(LciaResults, self).__setitem__(key, value)
        if key not in self._indices:
            self._indices.append(key)

    def add(self, value):
        # TODO: add should cumulate components if LciaResult is already present
        assert isinstance(value, LciaResult)
        self.__setitem__(value.quantity.uuid, value)

    def indices(self):
        for i in self._indices:
            yield i

    def to_list(self):
        return [self.__getitem__(k) for k in self._indices]

    def scale(self, factor):
        if factor == self._scale:
            return
        self._scale = factor
        for k in self._indices:
            self[k].set_scale(factor)

    def show(self):
        print('LCIA Results\n%s\n%s' % (self.entity, '-' * 60))
        if self._scale != 1.0:
            print('%60s: %10.4g' % ('scale', self._scale))
        for i, q in enumerate(self._indices):
            r = self[q]
            r.set_scale(self._scale)
            print('[%2d] %.3s  %10.5g %s' % (i, q, r.total(), r.quantity))

    def apply_weighting(self, weights, quantity, **kwargs):
        """
        Create a new LciaResult object containing the weighted sum of entries in the current object.

        We want the resulting LciaResult to still be aggregatable. In order to accomplish this, we need to maintain
        all the individual _LciaScores entities in the weighting inputs, and compute their weighted scores here. Then
        we need to log the weighted scores as the *node weights* and use *unit* values of unit scores, because
        SummaryLciaResults are only allowed to be further aggregated if they have the same unit score.

        This feels a bit hacky and may turn out to be a terrible idea.  But there is a certain harmony in making the
        quantity's unit THE unit for a weighting computation. So I think it will work for now.

        :param weights: a dict mapping quantity UUIDs to numerical weights
        :param quantity: EITHER an LcQuantity OR a string to use as the name of in LcQuantity.new()
        :param kwargs: passed to LciaResult
        :return:
        """
        weighted_result = LciaResult(quantity, **kwargs)

        component_list = dict()  # dict maps keys entities
        component_score = defaultdict(float)  # maps keys to weighted scores
        for method, weight in weights.items():
            try:
                result = self.__getitem__(method)  # an LciaResult
            except KeyError:
                continue
            for comp in result.keys():
                if comp in component_list.keys():
                    if result[comp].entity != component_list[comp]:
                        raise DuplicateResult('Key %s matches different entities:\n%s\n%s' % (comp,
                                                                                              result[comp],
                                                                                              component_list[comp]))
                else:
                    component_list[comp] = result[comp].entity
                component_score[comp] += (weight * result[comp].cumulative_result)

        for comp, ent in component_list.items():
            weighted_result.add_component(comp, entity=ent)
            weighted_result.add_summary(comp, ent, component_score[comp], 1.0)

        return weighted_result

    def clear(self):
        super(LciaResults, self).clear()
        self._indices = []

    def update(self, *args, **kwargs):
        super(LciaResults, self).update(*args, **kwargs)
        self._indices = list(self.keys())


class LciaWeighting(object):
    def __init__(self, quantity, weighting):
        """

        :param quantity: a new LcQuantity to represent the weighting
        :param weighting: a weighting dict as defined in apply_weighting
        """
        self._q = quantity
        self._w = weighting

    def weigh(self, res, **kwargs):
        return res.apply_weighting(self._w, self._q, **kwargs)

    def q(self):
        return self._q.get_uuid()


def traversal_to_lcia(ffs):
    """
    This function takes in a list of fragment flow records and aggregates their ScoreCaches into a set of LciaResults.
    The function is surprisingly slow, because AggregateLciaScore objects contain sets, so there is a lot of container
    checking. (I think that's why, anyway...)
    :param ffs:
    :return: dict of quantity uuid to LciaResult -> suitable for storing directly into a new term scorecache
    """
    results = LciaResults(ffs[0].fragment)
    for i in ffs:
        if not i.term.is_null:
            for q, v in i.term.score_cache_items():
                quantity = v.quantity

                if q not in results.keys():
                    results[q] = LciaResult(quantity, scenario=v.scenario)

                value = v.total()
                if value * i.node_weight == 0:
                    continue

                if i.term.direction == i.fragment.direction:
                    # if the directions collide (rather than complement), the term is getting run in reverse
                    value *= -1

                results[q].add_component(i.fragment.get_uuid(), entity=i)
                x = ExchangeValue(i.fragment, i.term.term_flow, i.term.direction, value=i.node_weight)
                try:
                    l = i.term.term_node.entity()['SpatialScope']
                except KeyError:
                    l = None
                f = Characterization(i.term.term_flow, quantity, value=value, location=l)
                results[q].add_score(i.fragment.get_uuid(), x, f, l)
    return results
