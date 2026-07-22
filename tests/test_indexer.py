import pytest
from app.indexer.parser import PythonParser
from app.indexer.graph import DependencyGraph, CallGraph

def test_python_parser():
    parser = PythonParser()
    sample_code = """
import os
import pandas as pd
from datetime import datetime as dt
from fastapi import FastAPI as FA

@custom_decorator
class ChildClass(ParentClass):
    \"\"\"This is a class docstring.\"\"\"
    
    @classmethod
    def perform_action(cls, x: int, y=10) -> str:
        \"\"\"This is a method docstring.\"\"\"
        print("Hello")
        pd.read_csv("data.csv")
        app = FA()
"""
    tree = parser.parse_code(sample_code.encode("utf-8"))
    
    # Extract symbols
    symbols = parser.extract_symbols(tree, sample_code)
    assert len(symbols) == 2
    
    class_sym = [s for s in symbols if s["type"] == "class"][0]
    assert class_sym["name"] == "ChildClass"
    assert class_sym["metadata"]["docstring"] == "This is a class docstring."
    assert class_sym["metadata"]["superclasses"] == ["ParentClass"]
    assert class_sym["metadata"]["decorators"] == ["custom_decorator"]

    method_sym = [s for s in symbols if s["type"] == "method"][0]
    assert method_sym["name"] == "ChildClass.perform_action"
    assert method_sym["metadata"]["docstring"] == "This is a method docstring."
    assert method_sym["metadata"]["decorators"] == ["classmethod"]
    assert method_sym["metadata"]["return_type"] == "str"
    
    params = method_sym["metadata"]["parameters"]
    assert len(params) == 3
    assert params[0]["name"] == "cls"
    assert params[1]["name"] == "x"
    assert params[1]["type"] == "int"
    assert params[2]["name"] == "y"
    assert params[2]["default"] == "10"

    # Extract imports and aliases
    imports, alias_map = parser.extract_imports_and_aliases(tree, sample_code)
    assert alias_map["pd"] == "pandas"
    assert alias_map["dt"] == "datetime.datetime"
    assert alias_map["FA"] == "fastapi.FastAPI"
    
    # Extract resolved calls
    calls = parser.extract_api_calls(tree, sample_code, alias_map)
    resolved_names = [c["resolved_name"] for c in calls]
    assert "pandas.read_csv" in resolved_names
    assert "fastapi.FastAPI" in resolved_names
    assert "print" in resolved_names


def test_dependency_graph():
    dep_graph = DependencyGraph()
    dep_graph.add_module("app.main")
    dep_graph.add_module("app.config")
    dep_graph.add_module("app.utils")
    
    # app.main imports app.config and app.utils
    dep_graph.add_dependency("app.main", "app.config")
    dep_graph.add_dependency("app.main", "app.utils")
    
    # Find impacted modules if app.utils is modified
    impacted = dep_graph.get_impacted_modules(["app.utils"])
    assert "app.main" in impacted
    assert "app.utils" in impacted
    assert "app.config" not in impacted


def test_call_graph():
    call_graph = CallGraph()
    call_graph.add_function("main_func", "app/main.py")
    call_graph.add_function("helper_func", "app/utils.py")
    call_graph.add_function("leaf_func", "app/helper.py")
    
    call_graph.add_call("main_func", "helper_func")
    call_graph.add_call("helper_func", "leaf_func")
    
    # Trace the calls reaching leaf_func
    paths = call_graph.get_call_chain("leaf_func")
    assert len(paths) > 0
    # One path should trace: main_func -> helper_func -> leaf_func
    found_path = False
    for p in paths:
        if p == ["main_func", "helper_func", "leaf_func"]:
            found_path = True
            break
    assert found_path is True
