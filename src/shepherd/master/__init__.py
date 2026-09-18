"""The orchestrator (D19), and the one package the vendor SDK may be imported in.

Deliberately empty of code. §5.0 puts `master/` at L5, so this package may reach
the system only through `toolsurface/`; `tests/boundaries` binds that rule to
this directory the moment the directory exists. Importing it must therefore cost
nothing and pull in nothing: T20 (`sdk_tools.py`) and T21 (`sdk_master.py`) both
import through here, and a module-scope vendor import placed here would load a
package shipping a 216,677,784-byte binary for every importer, which is exactly
the cost DP4 keeps out of every layer below this one.
"""
