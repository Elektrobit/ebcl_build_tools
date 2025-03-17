#!/bin/bash

clear

echo "=================== Linters ===================="

echo "------------------- Ruff -----------------------"

flake8 .

echo "------------------- Ruff -----------------------"

ruff check --output-format=github .

echo "------------------- darglint--------------------"

darglint --verbosity 2 --docstring-style google ebcl

echo "=================== Tests ===================="

coverage run -m pytest -v -s
coverage report -m
coverage html
