import runpy, os, sys
if len(sys.argv) < 2:
    print('Usage: run_validator_on_path.py <path_to_json_or_spine>')
    sys.exit(2)
path = sys.argv[1]
module_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'spine sorter 257.py'))
mod = runpy.run_path(module_path)
SpinePackageValidator = mod.get('SpinePackageValidator')
if not SpinePackageValidator:
    print('ERROR: SpinePackageValidator not found')
    sys.exit(1)
print('Running validator on:', path)
SpinePackageValidator.diagnose(path, log_callback=print)
