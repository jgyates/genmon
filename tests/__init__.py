# Makes tests/ a regular package, so "python -m unittest tests.<name>" finds
# genmon's tests even when a library installs its own top level "tests"
# package (bleson does; a regular package anywhere on the path wins over a
# folder without this file).
