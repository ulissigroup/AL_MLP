import numpy as np

# from al_mlp.ensemble_calc import EnsembleCalc

# from al_mlp.offline_active_learner import OfflineActiveLearner
from amptorch.trainer import AtomsTrainer
import os

# from al_mlp.base_calcs.dummy import Dummy
import torch

# from dask.distributed import Client, LocalCluster

# from al_mlp.atomistic_methods import Relaxation
# from ase.optimize import BFGS
import ase.io
from al_mlp.base_calcs.morse import MultiMorse
from al_mlp.preset_learners.ensemble_learner import EnsembleLearner


def run_offline_al(atomistic_method, images, dbname, parent_calc):

    Gs = {
        "default": {
            "G2": {
                "etas": np.logspace(np.log10(0.05), np.log10(5.0), num=4),
                "rs_s": [0] * 4,
            },
            "G4": {"etas": [0.005], "zetas": [1.0, 4.0], "gammas": [1.0, -1.0]},
            "cutoff": 5.876798323827276,
        },
    }

    elements = np.unique(images[0].get_chemical_symbols())

    learner_params = {
        "atomistic_method": atomistic_method,
        "max_iterations": 10,
        "force_tolerance": 0.01,
        "samples_to_retrain": 3,
        "filename": "relax_example",
        "file_dir": "./",
        "query_method": "max_uncertainty",
        "use_dask": True,
    }

    config = {
        "model": {"get_forces": True, "num_layers": 3, "num_nodes": 5},
        "optim": {
            "device": "cpu",
            "force_coefficient": 4.0,
            "lr": 1,
            "batch_size": 10,
            "epochs": 100,  # was 100
            "optimizer": torch.optim.LBFGS,
            "optimizer_args": {"optimizer__line_search_fn": "strong_wolfe"},
        },
        "dataset": {
            "raw_data": images,
            "val_split": 0,
            "elements": elements,
            "fp_params": Gs,
            "save_fps": False,
            "scaling": {"type": "standardize"},
        },
        "cmd": {
            "debug": False,
            "run_dir": "./",
            "seed": 1,
            "identifier": "test",
            "verbose": True,
            # "logger": True,
            "single-threaded": True,
        },
    }

    # if learner_params["use_dask"] and EnsembleCalc.executor is None:
    #    from dask.distributed import Client, LocalCluster

    #   cluster = LocalCluster(n_workers=4, processes=True, threads_per_worker=1)
    #  client = Client(cluster)
    # EnsembleCalc.set_executor(client)
    # cluster = LocalCluster(n_workers=4, processes=True, threads_per_worker=1)
    # client = Client(cluster)
    # EnsembleCalc.set_executor(client)

    trainer = AtomsTrainer(config)
    cutoff = Gs["default"]["cutoff"]
    base_calc = MultiMorse(images, cutoff, combo="mean")

    learner = EnsembleLearner(
        learner_params,
        trainer,
        images,
        parent_calc,
        base_calc,
        # ncores="max",
        ensemble=5,
    )

    learner.learn()

    al_iterations = learner.iterations - 1
    file_path = learner_params["file_dir"] + learner_params["filename"]
    final_ml_traj = ase.io.read("{}_iter_{}.traj".format(file_path, al_iterations), ":")

    if os.path.exists("dft_calls.db"):
        os.remove("dft_calls.db")
    # atomistic_method.run(learner, filename=dbname)

    return learner, final_ml_traj