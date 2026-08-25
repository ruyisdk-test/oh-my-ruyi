"""Child process entry points for isolated execution.

Child modules are intentionally not imported here. Each child is launched on
its own and importing this package must not initialize every command's ruyi
dependencies first.
"""
