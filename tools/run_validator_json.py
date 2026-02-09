import runpy, os
module_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'spine sorter 257.py'))
mod = runpy.run_path(module_path)
SpinePackageValidator = mod.get('SpinePackageValidator')
if not SpinePackageValidator:
    print('ERROR: SpinePackageValidator not found')
else:
    sample = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'test_files_from_collegues', 'me', 'spine_temp_1770640783_0', 'aambient.json'))
    print('Running validator on:', sample)
    SpinePackageValidator.diagnose(sample, log_callback=print)
