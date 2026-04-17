"""Parsing stage package for Forge.

Parse is the step in the Forge pipeline that turns each raw source file
(PDF, Word, Excel, images, email, ZIP, CAD, etc.) into a common parsed-text
shape. Later pipeline stages (chunk, enrich, embed, extract, export) all
read from that shared shape, so every parser in here returns the same
small record type no matter what the original file was.

Pipeline order: hash -> dedup -> skip/defer -> PARSE (this package) ->
chunk -> enrich -> embed -> extract -> export folder.
"""
