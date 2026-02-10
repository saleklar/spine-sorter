import runpy, os, sys
module_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'spine sorter 257.py'))
mod = runpy.run_path(module_path)
SpinePackageValidator = mod.get('SpinePackageValidator')
if not SpinePackageValidator:
    print('ERROR: SpinePackageValidator not found')
    sys.exit(2)
# file from test_files_from_collegues/me
sample = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'test_files_from_collegues', 'me', 'pop_ups.spine'))
print('Running validator on:', sample)
SpinePackageValidator.diagnose(sample, log_callback=print)
