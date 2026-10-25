"""
Root re-export shim for GenConsts - TradeSentinel Backend.
Allows seamless access to GenConsts from root-level scripts and modules.
"""

from app.core.genConsts import GenConsts

__all__ = ["GenConsts"]
