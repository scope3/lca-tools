"""
With inspiration from bw2data/io/import_ecospold2.py and affiliated files

The purpose of this archive (and ILCD alike) is to provide a common interface, a la the semantic
web paper, to a collection of process data, to wit:
 - list of process metadata:
   UUID | Name | Spatial | Temporal | Ref Product | Comment |

"""

from __future__ import print_function, unicode_literals

bytes = str
str = unicode

import os
import re

import uuid

from lxml import objectify

from lcatools.interfaces import BasicInterface, to_uuid
from lcatools.providers.archive import Archive
from lcatools.entities import LcUnit, LcQuantity, LcFlow, LcProcess
from lcatools.exchanges import Exchange


tail = re.compile('/([^/]+)$')


def not_none(x):
    return x if x is not None else ''


def _find_tag(o, tag, ns=None):
    """
    Deals with the fuckin' ILCD namespace shit
    :param o: objectified element
    :param tag:
    :return:
    """
    found = o.findall('.//{0}{1}'.format('{' + o.nsmap[ns] + '}', tag))
    return [''] if len(found) == 0 else found


class EcospoldVersionError(Exception):
    pass


class DirectionlessExchangeError(Exception):
    pass


class EcospoldV1Archive(BasicInterface):
    """
    Create an Ecospold Archive object from a path.  By default, assumes the path points to a literal
    .7z file, of the type that one can download from the ecoinvent website.  Creates an accessor for
    files in that archive and allows a user to
    """

    nsmap = 'http://www.EcoInvent.org/EcoSpold01'  # only valid for v1 ecospold files
    spold_version = tail.search(nsmap).groups()[0]

    def __init__(self, ref, prefix=None, ns_uuid=None, quiet=True):
        """
        Just instantiates the parent class.
        :param ref: just a reference
        :param prefix: difference between the internal path (ref) and the ILCD base
        :return:
        """
        super(EcospoldV1Archive, self).__init__(ref, quiet=quiet)
        self.internal_prefix = prefix
        self._archive = Archive(self.ref)

        # internal namespace UUID for generating keys
        ns_uuid = to_uuid(ns_uuid)
        self._ns_uuid = uuid.uuid4() if ns_uuid is None else ns_uuid

    def key_to_id(self, number):
        """
        Converts Ecospold01 "number" attributes to UUIDs using the internal UUID namespace.
        ASSUMPTION is that numbers are distinct across flows and processes - have not tested this rigorously
        :param number:
        :return:
        """
        return uuid.uuid3(self._ns_uuid, number.encode('utf-8'))

    def _build_prefix(self):
        path = ''
        if self.internal_prefix is not None:
            path = os.path.join(self.internal_prefix, path)
        return path

    def list_objects(self):
        assert self._archive.remote is False, "Cannot list objects for remote archives"
        return self._archive.listfiles(in_prefix=self._build_prefix())

    def _fetch_filename(self, filename):
        return self._archive.readfile(filename)

    def _get_objectified_entity(self, filename):
        o = objectify.fromstring(self._archive.readfile(filename))
        if o.nsmap[None] != self.nsmap:
            raise EcospoldVersionError('This class is for EcoSpold v%s only!' % self.nsmap[-2:])
        return o

    def _create_quantity(self, unitstring):
        """
        In ecospold v1, quantities are only units, defined by string
        :param unitstring:
        :return:
        """
        try_q = self.quantity_with_unit(unitstring)
        if try_q is None:
            ref_unit = LcUnit(unitstring)

            q = LcQuantity.new('EcoSpold Quantity %s' % unitstring, ref_unit, Comment=self.spold_version)
            q.set_external_ref(unitstring)
            self[q.get_uuid()] = q
        else:
            q = try_q

        return q

    def _create_flow(self, exch):
        """
        An ecospold01 exchange is really just a long attribute list, plus an inputGroup or outputGroup (ignored here)
        :param exch:
        :return:
        """
        number = exch.get('number')
        uid = self.key_to_id(number)
        if uid in self._entities:
            f = self[uid]
            assert f.entity_type == 'flow', "Expected flow, found %s" % f.entity_type

        else:
            # generate flow
            n = exch.get("name")
            q = self._create_quantity(exch.get("unit"))
            c = not_none(exch.get("generalComment"))
            cas = not_none(exch.get("CASNumber"))
            cat = [exch.get('category'), exch.get('subCategory')]

            f = LcFlow(uid, Name=n, ReferenceQuantity=q, CasNumber=cas, Comment=c, Compartment=cat)
            f.set_external_ref(int(number))
            self[uid] = f

        return f

    def _create_process(self, filename):
        """
        Extract dataset object from XML file
        :param filename:
        :return:
        """
        o = self._get_objectified_entity(filename)

        rf = None  # reference flow
        flowlist = []

        for exch in o.dataset.flowData.getchildren():
            f = self._create_flow(exch)
            if hasattr(exch, 'outputGroup'):
                d = 'Output'
                if exch.outputGroup == 0:
                    assert rf is None, "Multiple reference flows found!"
                    rf = f
            elif hasattr(exch, 'inputGroup'):
                d = 'Input'
            else:
                raise DirectionlessExchangeError
            flowlist.append((f, d))

        p_meta = o.dataset.metaInformation.processInformation
        n = p_meta.referenceFunction.get('name')

        u = self.key_to_id(n)

        if u in self._entities:
            p = self[u]
            assert p.entity_type == 'process', "Expected process, found %s" % p.entity_type

        else:
            # create new process
            g = p_meta.geography.get('location')
            stt = 'interval(%s, %s)' % (str(_find_tag(p_meta, 'startDate')[0]),
                                        str(_find_tag(p_meta, 'endDate')[0]))

            c = p_meta.referenceFunction.get('generalComment')

            cls = [p_meta.referenceFunction.get('category'), p_meta.referenceFunction.get('subCategory')]
            p = LcProcess(u, Name=n, Comment=c, SpatialScope=g, TemporalScope=stt,
                          Classifications=cls)
            p.set_external_ref(n)

            if rf is not None:
                p['ReferenceExchange'] = Exchange(p, rf, 'Output')

            self[u] = p

        for flow, f_dir in flowlist:
            self._add_exchange(Exchange(p, flow, f_dir))

        return p

    def _fetch(self, uid, **kwargs):
        """
        Nothing to do here-- if it's not found, it needs to be loaded
        :param uid:
        :param kwargs:
        :return:
        """
        print('No way to fetch by UUID. Loading all processes...')
        self.load_all()

    def _load_all(self):
        """
        No need to "fetch" with ecospold v1, since UUIDs are not known in advance.
        Instead, just load all the processes at once.
        :return:
        """
        for k in self.list_objects():
            self._create_process(k)
        self.check_counter('quantity')
        self.check_counter('flow')
        self.check_counter('process')

    def serialize(self, **kwargs):
        j = super(EcospoldV1Archive, self).serialize(**kwargs)
        if self.internal_prefix is not None:
            j['prefix'] = self.internal_prefix
        j['nsUuid'] = str(self._ns_uuid)
        return j
