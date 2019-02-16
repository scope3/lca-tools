import unittest
from lcatools.entities import LcQuantity

from ..quantity_manager import QuantitySynonyms, QuantityManager, QuantityUnitMismatch, QuantityAlreadySet


dummy_q = LcQuantity.new('A dummy quantity', 'dummy', Synonyms=['dumdum quantity', 'Qty Dummy'])
dummy_2 = LcQuantity.new('dumdum quantity', 'dummy')
dummy_x = LcQuantity.new('A dummy quantity', 'dooms')


class QuantityTest(unittest.TestCase):
    def test_create_new(self):
        qsyn = QuantitySynonyms.new(dummy_q)
        self.assertEqual(qsyn.unit, 'dummy')
        self.assertIs(qsyn.object, dummy_q)
        self.assertIs(qsyn.quantity, dummy_q)

    def test_assign(self):
        qsyn = QuantitySynonyms()
        qsyn.quantity = dummy_q
        self.assertEqual(qsyn.name, dummy_q['Name'])

    def test_merge(self):
        qsyn = QuantitySynonyms.new(dummy_q)
        qsyn2 = QuantitySynonyms.new(dummy_2)
        qsyn.add_child(qsyn2)
        self.assertTrue(qsyn.has_child(qsyn2))

    def test_already_set(self):
        qsyn = QuantitySynonyms.new(dummy_q)
        with self.assertRaises(QuantityAlreadySet):
            qsyn.quantity = dummy_2

    def test_conflicting_unit(self):
        qsyn = QuantitySynonyms.new(dummy_q)
        qsynx = QuantitySynonyms.new(dummy_x)
        with self.assertRaises(QuantityUnitMismatch):
            qsyn.add_child(qsynx)


class QuantityManagerTest(unittest.TestCase):
    def test_create(self):
        qmgr = QuantityManager()
        qmgr.add_quantity(dummy_q)
        self.assertIs(qmgr[dummy_q.uuid], dummy_q)
        syns = [x for x in qmgr.synonyms(dummy_q.uuid)]
        self.assertEqual(len(syns), 6)

    def test_synonyms(self):
        qmgr = QuantityManager()
        qmgr.add_quantity(dummy_2)
        self.assertSetEqual(set(qmgr.synonyms(dummy_2.uuid)), {dummy_2['Name'], dummy_2.link, dummy_2.uuid, str(dummy_2)})

    def test_child(self):
        qmgr = QuantityManager()
        qmgr.add_quantity(dummy_q)
        qmgr.add_quantity(dummy_2)
        self.assertIs(qmgr[dummy_2.uuid], dummy_q)

    def test_prune(self):
        qmgr = QuantityManager()
        qmgr.add_quantity(dummy_q)
        qmgr.add_quantity(dummy_x)
        self.assertIs(qmgr[dummy_x['Name']], dummy_q)
        self.assertIs(qmgr[dummy_x.uuid], dummy_x)


if __name__ == '__main__':
    unittest.main()
