# The fixtures hold planted-bug repos and hidden graders that fail on purpose on the
# unfixed code. They are run by run_eval.py in fresh copies, never by the repo suite.
collect_ignore_glob = ["fixtures/*"]
