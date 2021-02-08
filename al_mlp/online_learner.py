import copy
import os
import numpy as np
from ase.db import connect
from ase.calculators.singlepoint import SinglePointCalculator as sp
from ase.calculators.calculator import Calculator
from al_mlp.utils import convert_to_singlepoint, compute_with_calc
from al_mlp.bootstrap import non_bootstrap_ensemble
from al_mlp.ensemble_calc import EnsembleCalc
from al_mlp.calcs import DeltaCalc

__author__ = "Muhammed Shuaibi"
__email__ = "mshuaibi@andrew.cmu.edu"


class OnlineActiveLearner(Calculator):
    """Online Active Learner
    Parameters
    ----------
     learner_params: dict
         Dictionary of learner parameters and settings.

     trainer: object
         An isntance of a trainer that has a train and predict method.

     parent_dataset: list
         A list of ase.Atoms objects that have attached calculators.
         Used as the first set of training data.

     parent_calc: ase Calculator object
         Calculator used for querying training data.

     n_ensembles: int.
          n_ensemble of models to make predictions.

     n_cores: int.
          n_cores used to train ensembles.

     parent_calc: ase Calculator object
         Calculator used for querying training data.

     base_calc: ase Calculator object
         Calculator used to calculate delta data for training.

     trainer_calc: uninitialized ase Calculator object
         The trainer_calc should produce an ase Calculator instance
         capable of force and energy calculations via TrainerCalc(trainer)
    """

    implemented_properties = ["energy", "forces"]

    def __init__(
        self,
        learner_params,
        trainer,
        parent_dataset,
        parent_calc,
        base_calc,
        n_ensembles=10,
        n_cores="max",
    ):
        Calculator.__init__(self)

        self.n_ensembles = n_ensembles
        self.parent_dataset = parent_dataset
        self.parent_calc = parent_calc
        self.base_calc = base_calc
        self.calcs = [parent_calc, base_calc]
        self.trainer = trainer
        self.learner_params = learner_params
        self.n_cores = n_cores
        self.init_training_data()
        self.ensemble_calc = None
        self.trained_calc = None
        self.uncertainty_mod = learner_params["uncertain_tol"]
        self.parent_calls = 0

    def init_training_data(self):
        """
        Prepare the training data by attaching delta values for training.
        """
        raw_data = self.parent_dataset
        sp_raw_data = convert_to_singlepoint(raw_data)
        parent_ref_image = sp_raw_data[0]
        base_ref_image = compute_with_calc(sp_raw_data[:1], self.base_calc)[0]
        self.refs = [parent_ref_image, base_ref_image]
        self.delta_sub_calc = DeltaCalc(self.calcs, "sub", self.refs)
        parent_dataset = []
        self.ensemble_sets = []

    def get_uncertainty_tol(self, force_pred) -> float:
        """
        Gets the uncertainty tolerance to test the current model's uncertainty against
        Designed to be easily overwritten to return uncertainty tolerance in any way
        Arguments:
        Returns: uncertainty_tol (float)
        """
        uncertainty_tol = self.uncertainty_mod
        if (
            "relative_variance" in self.learner_params
            and self.learner_params["relative_variance"]
        ):
            # trained_calc_copy = copy.deepcopy(self.trained_calc)
            # copied_images = copy_images(self.parent_dataset)
            # base_uncertainty = 0
            # for image in copied_images:
            #    trained_calc_copy.reset()
            #    trained_calc_copy.get_forces(image)
            #    if image.info["uncertainty"][0] > base_uncertainty:
            #        base_uncertainty = image.info["uncertainty"][0]
            base_uncertainty = np.nanmax(np.abs(force_pred)) ** 2
            uncertainty_tol = self.uncertainty_mod * base_uncertainty
        return uncertainty_tol

    def call_parent(self, atoms) -> None:
        """
        Makes a parent call and obtains a new value which is added to parent dataset
        Trains a new ensemble on the dataset if the number of points is >1
        Sets the energy and forces results equal to the parent call values
        """

        print("Parent call required")
        db = connect("dft_calls.db")
        new_data = atoms.copy()
        new_data.set_calculator(copy.copy(self.parent_calc))

        # make a temporary directory for calling parent
        cwd = os.getcwd()
        os.makedirs("./temp", exist_ok=True)
        os.chdir("./temp")

        # make actual parent call to retrieve energies and forces
        energy_pred = new_data.get_potential_energy(apply_constraint=False)
        force_pred = new_data.get_forces(apply_constraint=False)
        sp_energy_force = sp(atoms=new_data, energy=energy_pred, forces=force_pred)
        sp_energy_force.implemented_properties = ["energy", "forces"]
        delta_sub_sp = DeltaCalc(
            (sp_energy_force, self.base_calc), "sub", self.refs
        )
        new_data.calc = delta_sub_sp
        new_data_list = convert_to_singlepoint([new_data])
        self.parent_calls += 1

        # delete the temporary directory
        os.chdir(cwd)
        os.system("rm -rf ./temp")

        # save parent call to call database
        try:
            db.write(new_data)
        except Exception:
            print("failed to write to db file")
            pass

        # add to parent_dataset
        self.ensemble_sets, self.parent_dataset = non_bootstrap_ensemble(
            self.parent_dataset,
            new_data_list,
            n_ensembles=self.n_ensembles,
        )

        # if parent_dataset is >1 point long, train a new ensemble on it
        if len(self.parent_dataset) > 1:
            self.ensemble_calc = EnsembleCalc.make_ensemble(
                self.ensemble_sets, self.trainer
            )
            self.trained_calc = DeltaCalc(
                [self.ensemble_calc, self.base_calc], "add", self.refs
            )

        # set energy and force results
        self.results["energy"] = energy_pred
        self.results["forces"] = force_pred

    def calculate(self, atoms, properties, system_changes) -> None:
        # call super calculate method
        Calculator.calculate(self, atoms, properties, system_changes)

        if len(self.parent_dataset) > 1:
            # if there is enough data to evaluate the ensemble:
            # evaluate the ensemble for the given point and get the uncertainty
            trained_calc_copy = copy.deepcopy(self.trained_calc)
            energy_pred = trained_calc_copy.get_potential_energy(atoms)
            force_pred = trained_calc_copy.get_forces(atoms)
            uncertainty = atoms.info["uncertainty"][0]

            # evaluate the current uncertainty tolerance
            uncertainty_tol = self.get_uncertainty_tol(force_pred)
            print(
                "uncertainty: "
                + str(uncertainty)
                + ", uncertainty_tol: "
                + str(uncertainty_tol)
            )

            if uncertainty >= uncertainty_tol:
                # call parent if uncertainty is above the tolerance
                self.call_parent(atoms)
            else:
                # otherise: set energy and force results
                self.results["energy"] = energy_pred
                self.results["forces"] = force_pred
        else:
            # otherwise: call the parent
            self.call_parent(atoms)
