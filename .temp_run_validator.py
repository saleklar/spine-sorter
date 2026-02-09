import runpy, os
ns = runpy.run_path(r"z:/spine sorter v257/spine sorter 257.py")
SpinePackageValidator = ns['SpinePackageValidator']
path = r"z:/spine sorter v257/test_files_from_collegues/me/anticipation.spine"
print('Running SpinePackageValidator.diagnose on:', path)
SpinePackageValidator.diagnose(path, log_callback=print)
