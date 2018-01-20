import unittest
from math import isclose

from .traci_2_1_spreadsheet import Traci21Factors

TRACI_2_1 = '/data/LCI/TRACI/traci_2_1_2014_dec_10_0_test.xlsx'  # note test file

NUM_METHODS = 10


class TraciTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        This is unfortunately very slow (~1.2 s), since xlrd reads the whole workbook ab initio
        :return:
        """
        cls._traci = Traci21Factors(TRACI_2_1)

    def setUp(self):
        self._qi = self._traci.make_interface('quantity')
        self._ii = self._traci.make_interface('index')

    def test_methods(self):
        self.assertEqual(len([m for m in self._ii.lcia_methods()]), NUM_METHODS)

    def test_ecotox(self):
        # note: UUID equality depends on the proper NS UUID being set in the invocation
        tox = self._qi.get('Ecotoxicity, freshwater')
        self.assertEqual(tox.uuid, 'f2bd6435-f825-3e7e-ab40-45ea5d1dc1d5')
        fac = next(self._qi.factors(tox.external_ref, flowable='ethyl carbamate', compartment='agricultural'))
        self.assertTrue(isclose(fac.value, 1.783221, rel_tol=1e-6))

    def test_compartments(self):
        cs = set(self._qi.compartments(flowable='ddd'))
        self.assertSetEqual(cs, {'agricultural', 'fresh water', 'rural air', 'sea water', 'soil', 'urban air'})


if __name__ == '__main__':
    unittest.main()
