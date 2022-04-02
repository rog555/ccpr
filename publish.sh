#!/bin/bash
pytest --cov=ccpr.py tests/ --cov-report html:/tmp/htmlcov --cov-fail-under 95
flake8 .
python setup.py sdist bdist_wheel
twine upload dist/ccpr-*-py2.py3-none-any.whl
rm -f dist/*