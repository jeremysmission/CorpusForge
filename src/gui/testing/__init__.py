"""Helpers for GUI-focused tests and harness code.

This subpackage is NOT used by an operator. It contains the "virtual
operator" harness: a headless boot helper and a behavioral engine that
discover and click buttons automatically so automated tests can
confirm the Forge GUI still works after a change. Nothing here runs
during a normal Forge session.
"""
