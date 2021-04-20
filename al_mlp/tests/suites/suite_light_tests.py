# tests/suite_light_tests.py
import unittest

# import test modules
from al_mlp.tests.cases.case_online_CuNP import online_CuNP
from al_mlp.tests.cases.case_offline_CuNP import offline_CuNP

# import and set executor client
from dask.distributed import Client, LocalCluster
from al_mlp.ml_potentials.amptorch_ensemble_calc import AmptorchEnsembleCalc

cluster = LocalCluster(n_workers=4, processes=True, threads_per_worker=1)
client = Client(cluster)
AmptorchEnsembleCalc.set_executor(client)

# initialize the test suite
loader = unittest.TestLoader()
suite = unittest.TestSuite()

# add tests to the test suite
suite.addTests(loader.loadTestsFromModule(online_CuNP))
suite.addTests(loader.loadTestsFromTestCase(offline_CuNP))

# Deprecated below, call using pytest instead
# initialize a runner, pass it your suite and run it
# runner = unittest.TextTestRunner(verbosity=3)
# if __name__ == "__main__":
#     result = runner.run(suite)
