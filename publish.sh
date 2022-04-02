#!/bin/bash
set -e
./test.sh
python setup.py sdist bdist_wheel
twine upload dist/ccpr-*-py2.py3-none-any.whl
rm -f dist/*