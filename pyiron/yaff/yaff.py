from pyiron import Project, ase_to_pyiron
from pyiron.base.generic.parameters import GenericParameters
from pyiron.atomistics.structure.atoms import Atoms
from pyiron.atomistics.job.atomistic import AtomisticGenericJob, GenericOutput
from pyiron.base.settings.generic import Settings

from yaff import System, log, ForceField
log.set_level(log.silent)
from molmod.units import *
from molmod.constants import *
from molmod.periodic import periodic as pt
import tamkin

import os, numpy as np, h5py, matplotlib.pyplot as pp


def write_chk(input_dict,working_directory='.'):
    # collect data and initialize Yaff system
    if 'cell' in input_dict.keys() and input_dict['cell'] is not None:
        system = System(input_dict['numbers'], input_dict['pos']*angstrom, rvecs=input_dict['cell']*angstrom)
    else:
        system = System(input_dict['numbers'], input_dict['pos']*angstrom)
    # determine masses, bonds and ffaypes from ffatype_rules
    system.detect_bonds()
    system.set_standard_masses()
    system.detect_ffatypes(input_dict['ffatype_rules'])
    # write dictionnairy to MolMod CHK file
    system.to_file(os.path.join(working_directory,'system.chk'))

def write_pars(input_dict,working_directory='.'):
    with open(os.path.join(working_directory,'pars.txt'), 'w') as f:
        for line in input_dict['ffpars']:
            f.write(line)

common = """#! /usr/bin/python

from molmod.units import *
from yaff import *
import h5py, numpy as np

#Setting up system and force field
system = System.from_file('system.chk')
ff = ForceField.generate(system, 'pars.txt', rcut={rcut}*angstrom, alpha_scale={alpha_scale}, gcut_scale={gcut_scale}, smooth_ei={smooth_ei})

#Setting up output
f = h5py.File('output.h5', mode='w')
hdf5 = HDF5Writer(f, step={h5step})
r = h5py.File('restart.h5', mode='w')
restart = RestartWriter(r, step=10000)

#Setting up simulation
"""

def write_yopt(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body += "dof = CartesianDOF(ff, gpos_rms={gpos_rms}, dpos_rms={dpos_rms})".format(
        gpos_rms=input_dict['gpos_rms'],dpos_rms=input_dict['dpos_rms']
    )
    body += """
opt = CGOptimizer(dof, hooks=[hdf5])
opt.run({nsteps})
""".format(nsteps=input_dict['nsteps'])
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def write_yopt_cell(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body += "dof = StrainCellDOF(ff, gpos_rms={gpos_rms}, dpos_rms={dpos_rms}, grvecs_rms={grvecs_rms}, drvecs_rms={drvecs_rms}, do_frozen=False)".format(
        gpos_rms=input_dict['gpos_rms'],dpos_rms=input_dict['dpos_rms'],
        grvecs_rms=input_dict['grvecs_rms'],drvecs_rms=input_dict['drvecs_rms']
    )
    body += """
opt = CGOptimizer(dof, hooks=[hdf5])
opt.run({nsteps})
""".format(nsteps=input_dict['nsteps'])
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def write_yhess(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body +="""dof = CartesianDOF(ff)

gpos  = np.zeros((len(system.numbers), 3), float)
vtens = np.zeros((3, 3), float)
energy = ff.compute(gpos, vtens)
hessian = estimate_hessian(dof, eps={hessian_eps})

system.to_hdf5(f)
f['system/energy'] = energy
f['system/gpos'] = gpos
f['system/hessian'] = hessian""".format(hessian_eps=input_dict['hessian_eps'])
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def write_ynve(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body += """timestep = {timestep}*femtosecond

vsl = VerletScreenLog(step=1000)
md = VerletIntegrator(ff, timestep, hooks=[hdf5, vsl, restart])
md.run({nsteps})
""".format(timestep=input_dict['timestep']/femtosecond, nsteps=input_dict['nsteps'])
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def write_ynvt(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body += """timestep = {timestep}*femtosecond
temp = {temp}*kelvin

thermo = NHCThermostat(temp, timecon={timecon_thermo}*femtosecond)

vsl = VerletScreenLog(step=1000)
md = VerletIntegrator(ff, timestep, hooks=[hdf5, thermo, vsl, restart])
md.run({nsteps})
""".format(
        temp=input_dict['temp']/kelvin,timestep=input_dict['timestep']/femtosecond,
        timecon_thermo=input_dict['timecon_thermo']/femtosecond, nsteps=input_dict['nsteps']
    )
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def write_ynpt(input_dict,working_directory='.'):
    body = common.format(
        rcut=input_dict['rcut']/angstrom, alpha_scale=input_dict['alpha_scale'],
        gcut_scale=input_dict['gcut_scale'], smooth_ei=input_dict['smooth_ei'],
        h5step=1,
    )
    body += """timestep = {timestep}*femtosecond
temp = {temp}*kelvin
press = {press}*bar

thermo = NHCThermostat(temp, timecon={timecon_thermo}*femtosecond)
baro = MTKBarostat(ff, temp, press, timecon={timecon_baro}*femtosecond)
TBC = TBCombination(thermo, baro)

vsl = VerletScreenLog(step=1000)
md = VerletIntegrator(ff, timestep, hooks=[hdf5, TBC, vsl, restart])
md.run({nsteps})
""".format(
        temp=input_dict['temp']/kelvin,timestep=input_dict['timestep']/femtosecond,
        press=input_dict['press']/bar,timecon_thermo=input_dict['timecon_thermo']/femtosecond,
        timecon_baro=input_dict['timecon_baro']/femtosecond, nsteps=input_dict['nsteps']
    )
    with open(os.path.join(working_directory,'yscript.py'), 'w') as f:
        f.write(body)

def hdf2dict(h5):
    hdict = {}
    hdict['structure/numbers'] = h5['system/numbers'][:]
    hdict['structure/masses'] = h5['system/masses'][:]
    hdict['structure/ffatypes'] = h5['system/ffatypes'][:]
    hdict['structure/ffatype_ids'] = h5['system/ffatype_ids'][:]
    if 'trajectory' in h5.keys() and 'pos' in h5['trajectory'].keys():
        hdict['generic/positions'] = h5['trajectory/pos'][:]/angstrom
    else:
        hdict['generic/positions'] = h5['system/pos'][:]/angstrom
    if 'trajectory' in h5.keys() and 'cell' in h5['trajectory']:
        hdict['generic/cells'] = h5['trajectory/cell'][:]/angstrom
    elif 'rvecs' in h5['system'].keys():
        hdict['generic/cells'] = h5['system/rvecs'][:]/angstrom
    else:
        hdict['generic/cells'] = None
    if 'trajectory' in h5.keys():
        if 'counter' in h5['trajectory'].keys():
            hdict['generic/steps'] = h5['trajectory/counter'][:]
        if 'time' in h5['trajectory'].keys():
            hdict['generic/time'] = h5['trajectory/time'][:]
        if 'volume' in h5['trajectory']:
            hdict['generic/volume'] = h5['trajectory/volume'][:]
        if 'epot' in h5['trajectory'].keys():
            hdict['generic/energy_pot'] = h5['trajectory/epot'][:]
        if 'ekin' in h5['trajectory'].keys():
            hdict['generic/energy_kin'] = h5['trajectory/ekin'][:]
        if 'temp' in h5['trajectory'].keys():
            hdict['generic/temperature'] = h5['trajectory/temp'][:]
        if 'etot' in h5['trajectory'].keys():
            hdict['generic/energy_tot'] = h5['trajectory/etot'][:]
        if 'econs' in h5['trajectory'].keys():
            hdict['generic/energy_cons'] = h5['trajectory/econs'][:]
        if 'press' in h5['trajectory'].keys():
            hdict['generic/pressure'] = h5['trajectory/press'][:]
        if 'gradient' in h5['trajectory'].keys():
            hdict['generic/forces'] = -h5['trajectory/gradient'][:]
    if 'hessian' in h5['system'].keys():
        hdict['generic/energy_tot'] = h5['system/energy'][()]
        hdict['generic/forces'] = -h5['system/gpos'][:]
        hdict['generic/hessian'] = h5['system/hessian'][:]
    return hdict

def collect_output(output_file):
    # this routine basically reads and returns the output HDF5 file produced by Yaff
    # read output
    h5 = h5py.File(output_file, mode='r')
    # translate to dict
    output_dict = hdf2dict(h5)
    return output_dict




class YaffInput(GenericParameters):
    def __init__(self, input_file_name=None):
        super(YaffInput, self).__init__(input_file_name=input_file_name,table_name="input_inp",comment_char="#")

    def load_default(self):
        """
        Loading the default settings for the input file.
        """
        input_str = """\
rcut 28.345892008818783 #(FF) real space cutoff
alpha_scale 3.2 #(FF) scale for ewald alpha parameter
gcut_scale 1.5 #(FF) scale for ewald reciprocal cutoff parameter
smooth_ei True #(FF) smoothen cutoff for real space electrostatics
gpos_rms 1e-8 #(OPT) convergence criterion for RMS of gradients towards atomic coordinates
dpos_rms 1e-6 #(OPT) convergence criterion for RMS of differences of atomic coordinates
grvecs_rms 1e-8 #(OPT) convergence criterion for RMS of gradients towards cell parameters
drvecs_rms 1e-6 #(OPT) convergence criterion for RMS of differences of cell parameters
hessian_eps 1e-3 #(HESS) step size in finite differences for numerical derivatives of the forces
timestep 41.341373336646825 #(MD) time step for verlet scheme
temp None #(MD) temperature
press None #(MD) pressure
timecon_thermo 4134.137333664683 #(MD) timeconstant for thermostat
timecon_baro 41341.37333664683 #(MD) timeconstant for barostat
nsteps 1000 #(GEN) number of steps for opt or md
"""
        self.load_string(input_str)




class YaffOutput(GenericOutput):
    """
    Handles the output from a Yaff simulation.
    Adds extra properties to handle for NMA
    """

    @property
    def numbers(self):
        return self._job['output/structure/numbers']

    @property
    def masses(self):
        return self._job['output/structure/masses']

    @property
    def hessian(self):
        return self._job['output/generic/hessian']




class Yaff(AtomisticGenericJob):
    def __init__(self, project, job_name):
        super(Yaff, self).__init__(project, job_name)
        self.__name__ = "Yaff"
        self._executable_activate(enforce=True)
        self.input = YaffInput()
        self.output = YaffOutput(job=self)
        self.jobtype = None

    def write_input(self):
        input_dict = {
            'jobtype': self.jobtype,
            'symbols': self.structure.get_chemical_symbols(),
            'numbers': np.array([pt[symbol].number for symbol in self.structure.get_chemical_symbols()]),
            'ffatype_rules': self.input['ffatype_rules'],
            'ffpars': self.input['ffpars'],
            'pos': self.structure.positions,
            'rcut': self.input['rcut'],
            'alpha_scale': self.input['alpha_scale'],
            'gcut_scale': self.input['gcut_scale'],
            'smooth_ei': self.input['smooth_ei'],
            'nsteps': self.input['nsteps'],
            'gpos_rms': self.input['gpos_rms'],
            'dpos_rms': self.input['dpos_rms'],
            'grvecs_rms': self.input['grvecs_rms'],
            'drvecs_rms': self.input['drvecs_rms'],
            'hessian_eps': self.input['hessian_eps'],
            'timestep': self.input['timestep'],
            'temp': self.input['temp'],
            'press': self.input['press'],
            'timecon_thermo': self.input['timecon_thermo'],
            'timecon_baro': self.input['timecon_baro'],
        }
        input_dict['cell'] = None
        if self.structure.cell is not None:
             input_dict['cell'] = self.structure.get_cell()
        write_chk(input_dict=input_dict,working_directory=self.working_directory)
        write_pars(input_dict=input_dict,working_directory=self.working_directory)
        if self.jobtype == 'opt':
            write_yopt(input_dict=input_dict,working_directory=self.working_directory)
        elif self.jobtype == 'opt_cell':
            write_yopt_cell(input_dict=input_dict,working_directory=self.working_directory)
        elif self.jobtype == 'hess':
            write_yhess(input_dict=input_dict,working_directory=self.working_directory)
        elif self.jobtype == 'nve':
            write_ynve(input_dict=input_dict,working_directory=self.working_directory)
        elif self.jobtype == 'nvt':
            write_ynvt(input_dict=input_dict,working_directory=self.working_directory)
        elif self.jobtype == 'npt':
            write_ynpt(input_dict=input_dict,working_directory=self.working_directory)
        else:
            raise IOError('Invalid job type for Yaff job, received %s' %self.jobtype)

    def collect_output(self):
        output_dict = collect_output(output_file=os.path.join(self.working_directory, 'output.h5'))
        with self.project_hdf5.open("output") as hdf5_output:
            for k, v in output_dict.items():
                hdf5_output[k] = v

    def to_hdf(self, hdf=None, group_name=None):
        super(Yaff, self).to_hdf(hdf=hdf, group_name=group_name)
        with self.project_hdf5.open("input") as hdf5_input:
            self.structure.to_hdf(hdf5_input)
            self.input.to_hdf(hdf5_input)
            hdf5_input['generic/jobtype'] = self.jobtype

    def from_hdf(self, hdf=None, group_name=None):
        super(Yaff, self).from_hdf(hdf=hdf, group_name=group_name)
        with self.project_hdf5.open("input") as hdf5_input:
            self.input.from_hdf(hdf5_input)
            self.structure = Atoms().from_hdf(hdf5_input)
            self.jobtype = hdf5_input['generic/jobtype']


    def get_structure(self, iteration_step=-1, wrap_atoms=True):
        """
        Overwrite the get_structure routine from AtomisticGenericJob because we want to avoid
        defining a unit cell when one does not exist
        """
        if not (self.structure is not None):
            raise AssertionError()

        positions = self.get("output/generic/positions")
        cells = self.get("output/generic/cells")

        snapshot = self.structure.copy()
        snapshot.positions = positions[iteration_step]
        if cells is not None:
            snapshot.cell = cells[iteration_step]
        indices = self.get("output/generic/indices")
        if indices is not None:
            snapshot.indices = indices[iteration_step]
        if wrap_atoms and cells is not None:
            return snapshot.center_coordinates_in_unit_cell()
        else:
            return snapshot

    def do_nma(self):
        mol = tamkin.Molecule(self.output.numbers, self.output.positions, self.output.masses, self.output.energy_tot, self.output.forces*-1, self.output.hessian)
        self.nma = tamkin.NMA(mol)

    def plot(self, ykey, xkey='generic/steps', xunit='au', yunit='au', ref=None, linestyle='-', rolling_average=False):
        xs = self['output/%s' %xkey]/parse_unit(xunit)
        ys = self['output/%s' %ykey]/parse_unit(yunit)
        if rolling_average:
            ra = np.zeros(len(ys))
            for i, y in enumerate(ys):
                if i==0:
                    ra[i] = ys[0]
                else:
                    ra[i] = (i*ra[i-1]+ys[i])/(i+1)
            ys = ra.copy()
            
        _ref(ys,ref)
        
        pp.clf()
        pp.plot(xs, ys, linestyle)
        pp.xlabel('%s [%s]' %(xkey, xunit))
        pp.ylabel('%s [%s]' %(ykey, yunit))
        pp.show()
        
        
    def plot_multi(self, ykeys, xkey='generic/steps', xunit='au', yunit='au', ref=None, linestyle='-', rolling_average=False):
        # Assume that all ykeys have the same length than the xkey
        xs  = self['output/%s' %xkey]/parse_unit(xunit)
        yss = np.array([self['output/%s' %ykey]/parse_unit(yunit) for ykey in ykeys])
        
        if rolling_average:
            for ys in yss:
                ra = np.zeros(len(ys))
                for i, y in enumerate(ys):
                    if i==0:
                        ra[i] = ys[0]
                    else:
                        ra[i] = (i*ra[i-1]+ys[i])/(i+1)
                ys = ra.copy()
                
        if not isinstance(ref,list):     
            for ys in yss:
                _ref(ys,ref)
        else:
            assert len(ref)==len(yss)
            for n in range(len(ref)):
                _ref(yss[n],ref[n])
                
        
        pp.clf()
        for n,ys in enuemrate(yss):
            pp.plot(xs, ys, linestyle, label=ykeys[n])
        pp.xlabel('%s [%s]' %(xkey, xunit))
        pp.ylabel('[%s]' %(yunit))
        pp.legend()
        pp.show()    
    
    def _ref(ys,ref):
        if isinstance(ref, int):
            ys -= ys[ref]
        elif isinstance(ref, float):
            ys -= ref
        elif isinstance(ref,str):
            if ref=='min':
                ys -= min(ys)
            elif ref=='max':
                ys -= max(ys)
            elif ref=='mean':
                ys -= np.mean(ys)

    def log(self):
        with open(os.path.join(self.working_directory, 'yaff.log')) as f:
            print(f.read())

    def get_yaff_system(self, snapshot=0):
        numbers = np.array([pt[symbol].number for symbol in self.structure.get_chemical_symbols()])
        if snapshot==0:
            struct = self.structure
        else:
            struct = self.get_structure(iteration_step=snapshot, wrap_atoms=False)
        pos = struct.positions.reshape(-1,3)
        cell = struct.cell
        if cell is None:
            system = System(numbers, pos*angstrom)
        else:
            system = System(numbers, pos*angstrom, rvecs=cell*angstrom)
        system.detect_bonds()
        system.set_standard_masses()
        system.detect_ffatypes(self.input['ffatype_rules'])
        return system

    def get_yaff_ff(self, system=None):
        if system is None:
            system = self.get_yaff_system()
        fn_pars = os.path.join(self.working_directory, 'pars.txt')
        if not os.path.isfile(fn_pars):
            raise IOError('No pars.txt file find in job working directory. Have you already run the job?')
        ff = ForceField.generate(
            system, fn_pars, rcut=self.input['rcut'], alpha_scale=self.input['alpha_scale'],
            gcut_scale=self.input['gcut_scale'], smooth_ei=self.input['smooth_ei']
        )
        return ff