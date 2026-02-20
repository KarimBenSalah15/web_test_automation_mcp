from __future__ import annotations

from typing import Any


class DomSnapshot:
    """Captures the current state of the DOM."""
    
    def __init__(self, accessibility_tree: Any) -> None:
        self.tree = accessibility_tree
        self.tree_hash = self._hash_tree(accessibility_tree)
    
    @staticmethod
    def _hash_tree(tree: Any) -> str:
        """Generate a simple hash of the tree structure."""
        import hashlib
        tree_str = str(tree)
        return hashlib.md5(tree_str.encode()).hexdigest()
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomSnapshot):
            return False
        return self.tree_hash == other.tree_hash


class DomDiffer:
    """Detects changes between two DOM snapshots."""
    
    def __init__(self, before: DomSnapshot, after: DomSnapshot) -> None:
        self.before = before
        self.after = after
    
    def has_changed(self) -> bool:
        """Check if DOM has changed between snapshots."""
        return self.before != self.after
    
    def get_summary(self) -> str:
        """Generate a human-readable summary of changes."""
        if self.has_changed():
            return "✅ DOM CHANGED"
        else:
            return "⚠️ DOM UNCHANGED"
    
    def get_change_description(self) -> str:
        """Get a description suitable for LLM analysis."""
        if not self.has_changed():
            return (
                "The DOM structure remained identical. "
                "The previous action either:\n"
                "  - Did not execute properly\n"
                "  - Had no visible effect on the page\n"
                "Consider trying a different selector or approach."
            )
        
        # For changed DOM, provide simple feedback
        return "The page structure has changed. The action appeared to have an effect."
