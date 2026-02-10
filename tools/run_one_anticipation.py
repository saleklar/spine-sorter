import runpy
import os

module_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'spine sorter 257.py'))
mod = runpy.run_path(module_path)
SpinePackageValidator = mod.get('SpinePackageValidator')
if not SpinePackageValidator:
    print('ERROR: SpinePackageValidator not found')
else:
    sample = r'T:/WORK/silverback/sorter_output/anticipation.spine'
    print('Running validator on:', sample)
    SpinePackageValidator.diagnose(sample, log_callback=print)
