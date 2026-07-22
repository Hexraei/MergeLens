import networkx as nx
from typing import Dict, List, Tuple

class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_module(self, module_name: str):
        """Adds a module node to the dependency graph."""
        self.graph.add_node(module_name, type="module")

    def add_dependency(self, source_module: str, target_module: str):
        """Adds an import dependency edge between modules."""
        self.graph.add_edge(source_module, target_module, relation="imports")

    def get_impacted_modules(self, modified_modules: List[str]) -> List[str]:
        """
        Calculates the blast radius of changes. Finds all modules that directly
        or indirectly import any of the modified modules (reverse search).
        """
        impacted = set()
        for mod in modified_modules:
            if not self.graph.has_node(mod):
                continue
            # Find all nodes that can reach `mod` in the graph
            # Since edges point from importer -> imported, we need to traverse in reverse direction
            ancestors = nx.ancestors(self.graph, mod)
            impacted.update(ancestors)
            impacted.add(mod)
        return list(impacted)


class CallGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_function(self, func_name: str, file_path: str):
        """Adds a function/method node to the call graph."""
        self.graph.add_node(func_name, file_path=file_path)

    def add_call(self, caller: str, callee: str):
        """Adds a call edge from caller function to callee function."""
        self.graph.add_edge(caller, callee)

    def get_call_chain(self, target_function: str) -> List[List[str]]:
        """
        Finds paths in the call graph that lead to the target function.
        Helps trace how a changed API usage bubbles up through the codebase.
        """
        if not self.graph.has_node(target_function):
            return []
        
        # We want to find all sources that can reach `target_function`
        # We can look for simple paths from any node to target_function
        chains = []
        for node in self.graph.nodes:
            if node == target_function:
                continue
            if nx.has_path(self.graph, node, target_function):
                # Get the shortest path as a representative trace
                path = nx.shortest_path(self.graph, node, target_function)
                chains.append(path)
        return chains
