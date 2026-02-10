import py_compile, sys
try:
    py_compile.compile(r'z:/spine sorter v257/spine sorter 257.py', doraise=True)
    print('COMPILE_OK')
except Exception as e:
    print('COMPILE_FAIL')
    print(repr(e))
    sys.exit(1)
