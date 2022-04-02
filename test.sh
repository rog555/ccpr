#!/bin/bash
set -e
pytest --cov=ccpr tests/ --cov-report html:/tmp/htmlcov --cov-fail-under 95
flake8 .