nothing:

clean:
	rm -f *.log

veryclean: clean
	rm -rf __pycache__ bebo/__pycache__ bebo.egg-info .pytest_cache \
	       .mypy_cache .coverage htmlcov

potest:
	poetry run pytest tests

pocov:
	poetry run coverage run -m pytest tests
	poetry run coverage html
	poetry run coverage report

poflake:
	poetry run flake8 bebo tests

potype:
	poetry run python -m mypy bebo --include 'bebo*'
