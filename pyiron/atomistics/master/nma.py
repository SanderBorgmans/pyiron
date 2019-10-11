# coding: utf-8
# Copyright (c) Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department
# Distributed under the terms of "New BSD License", see the LICENSE file.

from __future__ import print_function

import numpy as np
import scipy.integrate
import scipy.optimize as spy
import scipy.constants
import warnings
from pyiron.atomistics.master.parallel import AtomisticParallelMaster
from pyiron.base.master.parallel import JobGenerator



# ToDo: not all abstract methods implemented
class NMA(AtomisticParallelMaster):
    def __init__(self, project, job_name='nma'):
        """

        Args:
            project:
            job_name:
        """
        super(NMA, self).__init__(project, job_name)
        self.__name__ = 'NMA'
        self.__version__ = '0.1.0'

        # print ("h5_path: ", self.project_hdf5._h5_path)

        # define default input
        self.input['num_points'] = (11, 'number of sample points')
        self.input['fit_type'] = ("polynomial", "['polynomial', 'birch', 'birchmurnaghan', 'murnaghan', 'pouriertarantola', 'vinet']")
        self.input['fit_order'] = (3, 'order of the fit polynom')
        self.input['vol_range'] = (0.1, 'relative volume variation around volume defined by ref_ham')

        self.debye_model = DebyeModel(self)
        self.fit_module = EnergyVolumeFit()

        self.fit_dict = None
        self._debye_T = None
        self._job_generator = MurnaghanJobGenerator(self)

        
###########################
        
    def do_nma(self):
        mol = tamkin.Molecule(self.output.numbers, self.output.positions*angstrom, self.output.masses, self.output.energy_tot*electronvolt,
                                                   self.output.forces *-1 * electronvolt/angstrom, self.output.hessian * electronvolt/angstrom**2)
        self.nma = tamkin.NMA(mol)

    def animate_nma_mode(self,index,amplitude=1.0,frames=24,spacefill=False,particle_size=0.5):
        print("This mode corresponds to a frequency of {} cm^-1".format(self.nma.freqs[index]/lightspeed/(1./centimeter)))
        coordinates = self.nma.coordinates
        symbols = [periodic[n].symbol for n in self.nma.numbers]

        mode = self.nma.modes[:,index]
        if self.nma.masses3 is not None:
            mode /= np.sqrt(self.nma.masses3)
        mode /= np.linalg.norm(mode)

        positions = np.zeros((frames,len(symbols),3))

        for frame in range(frames):
            factor = amplitude*np.sin(2*np.pi*float(frame)/frames)
            positions[frame] = (coordinates + factor*mode.reshape((-1,3)))/angstrom

        try:
            import nglview
        except ImportError:
            raise ImportError("The animate_nma_mode() function requires the package nglview to be installed")

        animation = nglview.show_asetraj(Trajectory(positions,self.structure))
        if spacefill:
            animation.add_spacefill(radius_type='vdw', scale=0.5, radius=particle_size)
            animation.remove_ball_and_stick()
        else:
            animation.add_ball_and_stick()
        return animation

    def plot_IR_spectrum(self,width=10,scale=1.0):
        """
        Plot IR spectrum based on Lorentzian width
        Read from log file, implementing calculation of intensities from fchk would be cumbersome
        """
        # Read IR intensities from log file
        path = self.path+'_hdf5/'+self.name+'/input.log'
        ir_int = np.zeros(len(self.nma.freqs)-len(self.nma.zeros)) # get number of ir_intensities
        with open(path,'r') as f:
            lines = f.readlines()

        # Assert normal termination
        assert "Normal termination of Gaussian" in lines[-1]

        counter=0
        for line in lines:
            if 'IR Inten    --' in line:
                ints = np.array([float(i) for i in line[15:].split()])
                ir_int[counter:counter+len(ints)] = ints
                counter+=len(ints)


        def Lorentz(x,p,w):
            """
            Lorentzian line shape function, p is position of max, w is FWHM and x is current frequency
            """
            return 1./(1.+((p-x)/(w/2.))**2)

        freqs = self.nma.freqs/lightspeed/(1./centimeter) * scale
        xr = np.linspace(0,4000,1000)
        yr = np.zeros(xr.shape)

        for n,intensity in enumerate(ir_int):
            print(freqs[len(self.nma.zeros)+n],intensity)
            yr+=intensity*Lorentz(xr,freqs[len(self.nma.zeros)+n],width)

        pt.figure()
        pt.plot(xr,yr)
        pt.xlabel(r'Frequency (cm$^{-1}$)')
        pt.ylabel('Intensity (a.u.)')
        pt.show()

###########################        
        
    @property
    def fit(self):
        return self.debye_model

    @property
    def equilibrium_volume(self):
        return self.fit_dict["volume_eq"]

    @property
    def equilibrium_energy(self):
        return self.fit_dict["energy_eq"]

    def fit_polynomial(self, fit_order=3, vol_erg_dic=None):
        return self.poly_fit(fit_order=fit_order, vol_erg_dic=vol_erg_dic)

    def fit_murnaghan(self, vol_erg_dic=None):
        return self._fit_eos_general(vol_erg_dic=vol_erg_dic, fittype='murnaghan')

    def fit_birch_murnaghan(self, vol_erg_dic=None):
        return self._fit_eos_general(vol_erg_dic=vol_erg_dic, fittype='birchmurnaghan')

    def fit_vinet(self, vol_erg_dic=None):
        return self._fit_eos_general(vol_erg_dic=vol_erg_dic, fittype='vinet')

    def _fit_eos_general(self, vol_erg_dic=None, fittype='birchmurnaghan'):
        self._set_fit_module(vol_erg_dic=vol_erg_dic)
        fit_dict = self.fit_module.fit_eos_general(fittype=fittype)
        self.input['fit_type'] = fit_dict["fit_type"]
        self.input['fit_order'] = 0
        with self.project_hdf5.open('input') as hdf5_input:
            self.input.to_hdf(hdf5_input)
        with self.project_hdf5.open("output") as hdf5:
            hdf5["equilibrium_energy"] = fit_dict["energy_eq"]
            hdf5["equilibrium_volume"] = fit_dict["volume_eq"]
            hdf5["equilibrium_bulk_modulus"] = fit_dict["bulkmodul_eq"]
            hdf5["equilibrium_b_prime"] = fit_dict["b_prime_eq"]

        self.fit_dict = fit_dict
        return fit_dict

    def _fit_leastsq(self, volume_lst, energy_lst, fittype='birchmurnaghan'):
        return self.fit_module._fit_leastsq(volume_lst=volume_lst, energy_lst=energy_lst, fittype=fittype)

    def _set_fit_module(self, vol_erg_dic=None):
        if vol_erg_dic is not None:
            if "volume" in vol_erg_dic.keys() and "energy" in vol_erg_dic.keys():
                self.fit_module = EnergyVolumeFit(volume_lst=vol_erg_dic["volume"], energy_lst=vol_erg_dic["energy"])
            else:
                raise KeyError
        else:
            df = self.output_to_pandas()
            self.fit_module = EnergyVolumeFit(volume_lst=df["volume"].values, energy_lst=df["energy"].values)

    def poly_fit(self, fit_order=3, vol_erg_dic=None):
        self._set_fit_module(vol_erg_dic=vol_erg_dic)
        fit_dict = self.fit_module.fit_polynomial(fit_order=fit_order)
        if fit_dict is None:
            self._logger.warning("Minimum could not be found!")
        else:
            self.input['fit_type'] = fit_dict["fit_type"]
            self.input['fit_order'] = fit_dict["fit_order"]
            with self.project_hdf5.open('input') as hdf5_input:
                self.input.to_hdf(hdf5_input)
            with self.project_hdf5.open("output") as hdf5:
                hdf5["equilibrium_energy"] = fit_dict["energy_eq"]
                hdf5["equilibrium_volume"] = fit_dict["volume_eq"]
                hdf5["equilibrium_bulk_modulus"] = fit_dict["bulkmodul_eq"]
                hdf5["equilibrium_b_prime"] = fit_dict["b_prime_eq"]

            with self._hdf5.open("output") as hdf5:
                self.get_structure(iteration_step=-1).to_hdf(hdf5)

            self.fit_dict = fit_dict
        return fit_dict

    def list_structures(self):
        if self.ref_job.structure is not None:
            return [parameter[1] for parameter in self._job_generator.parameter_list]
        else:
            return []

    def collect_output(self):
        if self.server.run_mode.interactive:
            ham = self.project_hdf5.inspect(self.child_ids[0])
            erg_lst = ham["output/generic/energy_tot"]
            vol_lst = ham["output/generic/volume"]
            arg_lst = np.argsort(vol_lst)

            self._output["volume"] = vol_lst[arg_lst]
            self._output["energy"] = erg_lst[arg_lst]
        else:
            erg_lst, vol_lst, err_lst, id_lst = [], [], [], []
            for job_id in self.child_ids:
                ham = self.project_hdf5.inspect(job_id)
                print('job_id: ', job_id, ham.status)
                energy = ham["output/generic/energy_tot"][-1]
                volume = ham["output/generic/volume"][-1]
                erg_lst.append(np.mean(energy))
                err_lst.append(np.var(energy))
                vol_lst.append(volume)
                id_lst.append(job_id)
            vol_lst = np.array(vol_lst)
            erg_lst = np.array(erg_lst)
            err_lst = np.array(err_lst)
            id_lst = np.array(id_lst)
            arg_lst = np.argsort(vol_lst)

            self._output["volume"] = vol_lst[arg_lst]
            self._output["energy"] = erg_lst[arg_lst]
            self._output["error"] = err_lst[arg_lst]
            self._output["id"] = id_lst[arg_lst]

        with self.project_hdf5.open("output") as hdf5_out:
            for key, val in self._output.items():
                hdf5_out[key] = val
        if self.input['fit_type'] == "polynomial":
            self.fit_polynomial(fit_order=self.input['fit_order'])
        else:
            self._fit_eos_general(fittype=self.input['fit_type'])

    def plot(self, num_steps=100, plt_show=True):
        try:
            import matplotlib.pylab as plt
        except ImportError:
            import matplotlib.pyplot as plt
        if not self.fit_dict:
            if self.input['fit_type'] == "polynomial":
                self.fit_polynomial(fit_order=self.input['fit_order'])
            else:
                self._fit_eos_general(fittype=self.input['fit_type'])
        df = self.output_to_pandas()
        vol_lst, erg_lst = df["volume"].values, df["energy"].values
        x_i = np.linspace(np.min(vol_lst), np.max(vol_lst), num_steps)
        color = 'blue'

        if self.fit_dict is not None:
            if self.input['fit_type'] == "polynomial":
                p_fit = np.poly1d(self.fit_dict["poly_fit"])
                least_square_error = self.fit_module.get_error(vol_lst, erg_lst, p_fit)
                plt.title("Murnaghan: error: " + str(least_square_error))
                plt.plot(x_i, p_fit(x_i), '-', label=self.input['fit_type'], color=color, linewidth=3)
            else:
                V0 = self.fit_dict["volume_eq"]
                E0 = self.fit_dict["energy_eq"]
                B0 = self.fit_dict["bulkmodul_eq"]
                BP = self.fit_dict["b_prime_eq"]
                if self.input['fit_type'].lower() == 'birchmurnaghan':
                    eng_fit_lst = birchmurnaghan_energy(x_i, E0, B0 / eV_div_A3_to_GPa, BP, V0)
                elif self.input['fit_type'].lower() == 'vinet':
                    eng_fit_lst = vinet_energy(x_i, E0, B0 / eV_div_A3_to_GPa, BP, V0)
                elif self.input['fit_type'].lower() == 'murnaghan':
                    eng_fit_lst = murnaghan(x_i, E0, B0 / eV_div_A3_to_GPa, BP, V0)
                elif self.input['fit_type'].lower() == 'pouriertarantola':
                    eng_fit_lst = pouriertarantola(x_i, E0, B0 / eV_div_A3_to_GPa, BP, V0)
                elif self.input['fit_type'].lower() == 'birch':
                    eng_fit_lst = birch(x_i, E0, B0, BP, V0)
                else:
                    raise ValueError
                plt.plot(x_i, eng_fit_lst, '-', label=self.input['fit_type'], color=color, linewidth=3)

        plt.plot(vol_lst, erg_lst, 'x', color=color, markersize=20)
        plt.legend()
        plt.xlabel("Volume ($\AA^3$)")
        plt.ylabel("energy (eV)")
        if plt_show:
            plt.show()

    def get_structure(self, iteration_step=-1):
        """

        Returns: Structure with equilibrium volume

        """
        if not (self.structure is not None):
            raise AssertionError()
        if iteration_step == -1:
            snapshot = self.structure.copy()
            old_vol = snapshot.get_volume()
            new_vol = self["output/equilibrium_volume"]
            k = (new_vol / old_vol) ** (1. / 3.)
            new_cell = snapshot.cell * k
            snapshot.set_cell(new_cell, scale_atoms=True)
            return snapshot
        elif iteration_step == 0:
            return self.structure
        else:
            raise ValueError('iteration_step should be either 0 or -1.')