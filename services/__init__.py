"""Business logic.

Nothing in this package imports Flask. Routes parse and serialise; these
modules decide. That boundary is what lets the mock backend be swapped for the
parent platform's API later without touching the UI or the route layer.
"""
