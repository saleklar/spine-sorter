import runpy
import os

module_path = os.path.join(os.path.dirname(__file__), '..', 'spine sorter 257.py')
module_path = os.path.normpath(module_path)

g = runpy.run_path(module_path)
SpinePackageValidator = g.get('SpinePackageValidator')
if not SpinePackageValidator:
    print('ERROR: SpinePackageValidator not found in module')
else:
    sample = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'test_files_from_collegues', 'muthahar', 'ambient.spine'))
    print('Running validator on:', sample)
    SpinePackageValidator.diagnose(sample, log_callback=print)
