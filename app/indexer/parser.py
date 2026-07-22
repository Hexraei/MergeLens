from typing import Dict, List, Any, Tuple, Optional
import tree_sitter_languages

class PythonParser:
    def __init__(self):
        # Obtain parser using tree-sitter-languages which bundles compiled grammars
        self.parser = tree_sitter_languages.get_parser("python")

    def parse_code(self, code_bytes: bytes) -> Any:
        """Parses source code bytes into a tree-sitter Tree."""
        return self.parser.parse(code_bytes)

    def _extract_docstring(self, body_node: Any, source_code: str) -> str:
        """Helper to extract docstring from the first statement of a class/function block."""
        if not body_node or body_node.type != "block":
            return ""
        
        # Check first child statement
        if len(body_node.children) > 0:
            first_stmt = body_node.children[0]
            # E.g. expression_statement -> string
            if first_stmt.type == "expression_statement" and len(first_stmt.children) > 0:
                child = first_stmt.children[0]
                if child.type == "string":
                    raw_str = source_code[child.start_byte:child.end_byte]
                    # Strip quotes (triple or single)
                    for q in ['"""', "'''", '"', "'"]:
                        if raw_str.startswith(q) and raw_str.endswith(q):
                            return raw_str[len(q):-len(q)].strip()
                    return raw_str.strip()
        return ""

    def _extract_superclasses(self, class_node: Any, source_code: str) -> List[str]:
        """Extract base classes from class inheritance clause."""
        bases = []
        superclasses_node = class_node.child_by_field_name("superclasses")
        if superclasses_node:
            for base_node in superclasses_node.children:
                if base_node.type not in ["(", ")", ","]:
                    bases.append(source_code[base_node.start_byte:base_node.end_byte].strip())
        return bases

    def _extract_parameters(self, func_node: Any, source_code: str) -> List[Dict[str, Any]]:
        """Extract list of parameters with names, type annotations, and default values."""
        params = []
        parameters_node = func_node.child_by_field_name("parameters")
        if not parameters_node:
            return params

        for param_node in parameters_node.children:
            # Skip punctuation like commas or parentheses
            if param_node.type in ["(", ")", ",", "*", "/"]:
                continue
            
            p_info = {"name": "", "type": None, "default": None}
            
            if param_node.type == "identifier":
                p_info["name"] = source_code[param_node.start_byte:param_node.end_byte].strip()
            
            elif param_node.type == "typed_parameter":
                # E.g. x: int
                name_node = param_node.children[0]
                p_info["name"] = source_code[name_node.start_byte:name_node.end_byte].strip()
                type_node = param_node.children[-1]
                p_info["type"] = source_code[type_node.start_byte:type_node.end_byte].strip()
                
            elif param_node.type == "default_parameter":
                # E.g. x = 10 or x: int = 10
                name_node = param_node.children[0]
                value_node = param_node.children[-1]
                p_info["default"] = source_code[value_node.start_byte:value_node.end_byte].strip()
                
                # Check if it has a type annotation (typed parameter as name)
                if name_node.type == "typed_parameter":
                    n_node = name_node.children[0]
                    p_info["name"] = source_code[n_node.start_byte:n_node.end_byte].strip()
                    type_node = name_node.children[-1]
                    p_info["type"] = source_code[type_node.start_byte:type_node.end_byte].strip()
                else:
                    p_info["name"] = source_code[name_node.start_byte:name_node.end_byte].strip()
                    
            elif param_node.type in ["dictionary_splat_pattern", "list_splat_pattern"]:
                # E.g. *args or **kwargs
                p_info["name"] = source_code[param_node.start_byte:param_node.end_byte].strip()
            
            if p_info["name"]:
                params.append(p_info)

        return params

    def _extract_return_type(self, func_node: Any, source_code: str) -> Optional[str]:
        """Extract return type annotation from function definition."""
        ret_node = func_node.child_by_field_name("return_type")
        if ret_node:
            return source_code[ret_node.start_byte:ret_node.end_byte].strip()
        return None

    def extract_symbols(self, tree: Any, source_code: str) -> List[Dict[str, Any]]:
        """
        Traverses the AST tree and extracts deep descriptions of classes, functions, and methods.
        Returns detailed structured symbols.
        """
        symbols = []
        root_node = tree.root_node

        def traverse(node, current_class: Optional[str] = None, decorators: List[str] = None):
            if decorators is None:
                decorators = []

            # If decorated definition, extract decorators and pass down to inner definition
            if node.type == "decorated_definition":
                local_decos = []
                inner_definition = None
                for child in node.children:
                    if child.type == "decorator":
                        # E.g. @classmethod or @deco(arg)
                        # Decorator's child is usually an identifier or a call
                        deco_node = child.children[-1]  # Exclude the '@'
                        local_decos.append(source_code[deco_node.start_byte:deco_node.end_byte].strip())
                    elif child.type in ["function_definition", "class_definition"]:
                        inner_definition = child
                
                if inner_definition:
                    traverse(inner_definition, current_class, local_decos)
                return

            if node.type == "class_definition":
                name_node = None
                body_node = None
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                    elif child.type == "block":
                        body_node = child
                
                if name_node:
                    class_name = source_code[name_node.start_byte:name_node.end_byte].strip()
                    docstring = self._extract_docstring(body_node, source_code)
                    bases = self._extract_superclasses(node, source_code)
                    
                    symbols.append({
                        "name": class_name,
                        "type": "class",
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "metadata": {
                            "docstring": docstring,
                            "superclasses": bases,
                            "decorators": decorators
                        }
                    })
                    
                    # Traverse class body looking for methods
                    if body_node:
                        for body_child in body_node.children:
                            traverse(body_child, current_class=class_name)
                return

            if node.type == "function_definition":
                name_node = None
                body_node = None
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                    elif child.type == "block":
                        body_node = child
                
                if name_node:
                    func_name = source_code[name_node.start_byte:name_node.end_byte].strip()
                    docstring = self._extract_docstring(body_node, source_code)
                    params = self._extract_parameters(node, source_code)
                    ret_type = self._extract_return_type(node, source_code)
                    
                    symbols.append({
                        "name": f"{current_class}.{func_name}" if current_class else func_name,
                        "type": "method" if current_class else "function",
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "metadata": {
                            "docstring": docstring,
                            "parameters": params,
                            "return_type": ret_type,
                            "decorators": decorators,
                            "class_name": current_class
                        }
                    })
                return

            # For general nodes, traverse children
            for child in node.children:
                traverse(child, current_class)

        traverse(root_node)
        return symbols

    def extract_imports_and_aliases(self, tree: Any, source_code: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Parses import statements.
        Returns:
          - A list of imports for database tracking.
          - A dictionary mapping local names/aliases to their fully qualified import modules.
        """
        imports = []
        alias_map = {}
        root_node = tree.root_node

        def traverse(node):
            if node.type == "import_statement":
                # E.g. import os, sys
                # E.g. import pandas as pd
                # We can check children for dotted_name and aliased_import
                for child in node.children:
                    if child.type == "dotted_name":
                        mod_name = source_code[child.start_byte:child.end_byte].strip()
                        imports.append({
                            "type": "import",
                            "module": mod_name,
                            "line": node.start_point[0] + 1
                        })
                        alias_map[mod_name] = mod_name
                    elif child.type == "aliased_import":
                        # E.g. pandas as pd
                        name_node = child.children[0]
                        alias_node = child.children[-1]
                        mod_name = source_code[name_node.start_byte:name_node.end_byte].strip()
                        alias_name = source_code[alias_node.start_byte:alias_node.end_byte].strip()
                        imports.append({
                            "type": "import_alias",
                            "module": mod_name,
                            "alias": alias_name,
                            "line": node.start_point[0] + 1
                        })
                        alias_map[alias_name] = mod_name

            elif node.type == "import_from_statement":
                # E.g. from fastapi import FastAPI as FA
                # E.g. from os import path
                # First child (or dotted_name child) is the source module
                from_mod = ""
                for child in node.children:
                    if child.type == "dotted_name":
                        from_mod = source_code[child.start_byte:child.end_byte].strip()
                        break
                
                # Look at the imported names
                # They can be inside wildcards, identifiers, or aliased_import
                for child in node.children:
                    if child.type == "wildcard_import":
                        imports.append({
                            "type": "import_from_wildcard",
                            "module": from_mod,
                            "line": node.start_point[0] + 1
                        })
                    elif child.type == "dotted_name" and child != node.children[1]:
                        # Multiple imported items without 'from' module or other structures
                        pass
                
                # Check for specific children
                # Usually there's an import_list or named children
                def extract_from_list(n):
                    if n.type == "aliased_import":
                        orig_name = source_code[n.children[0].start_byte:n.children[0].end_byte].strip()
                        alias_name = source_code[n.children[-1].start_byte:n.children[-1].end_byte].strip()
                        full_mod = f"{from_mod}.{orig_name}"
                        imports.append({
                            "type": "import_from_alias",
                            "module": full_mod,
                            "alias": alias_name,
                            "line": node.start_point[0] + 1
                        })
                        alias_map[alias_name] = full_mod
                    elif n.type == "identifier":
                        item_name = source_code[n.start_byte:n.end_byte].strip()
                        full_mod = f"{from_mod}.{item_name}"
                        imports.append({
                            "type": "import_from",
                            "module": full_mod,
                            "line": node.start_point[0] + 1
                        })
                        alias_map[item_name] = full_mod

                # Traverse children recursively to find identifiers or aliased imports inside import lists
                def walk_imports(n):
                    if n.type in ["aliased_import", "identifier"]:
                        extract_from_list(n)
                        return
                    for c in n.children:
                        if c.type not in ["dotted_name", "from", "import"]:
                            walk_imports(c)

                walk_imports(node)

            for child in node.children:
                traverse(child)

        traverse(root_node)
        return imports, alias_map

    def extract_api_calls(self, tree: Any, source_code: str, alias_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Extracts API calls and resolves them using the alias map.
        E.g. pd.read_csv(...) -> resolves pd to pandas -> returns "pandas.read_csv"
        """
        calls = []
        root_node = tree.root_node

        def traverse(node):
            if node.type == "call":
                func_node = node.children[0]
                raw_name = source_code[func_node.start_byte:func_node.end_byte].strip()
                
                # Resolve name using alias map
                resolved_name = raw_name
                parts = raw_name.split(".")
                if parts[0] in alias_map:
                    resolved_name = ".".join([alias_map[parts[0]]] + parts[1:])

                calls.append({
                    "name": raw_name,
                    "resolved_name": resolved_name,
                    "line": node.start_point[0] + 1,
                })

            for child in node.children:
                traverse(child)

        traverse(root_node)
        return calls
