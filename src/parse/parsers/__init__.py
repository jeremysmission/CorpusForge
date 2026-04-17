"""Concrete parser implementations for each supported file type.

Each module in this folder handles one file format (or family of formats)
and turns its bytes into clean text plus a small amount of metadata.
The dispatcher in the parent package decides which parser to use based
on the file extension.
"""
