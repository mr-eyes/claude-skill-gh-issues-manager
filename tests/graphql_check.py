"""A small GraphQL query reader for the tests.

It parses the selection set of a query and checks every field against an
excerpt of GitHub's public schema, so a query that names a field GitHub does
not have fails here instead of on GitHub. Used by the tests and by fake_gh.py,
which refuses queries the same way the real API would.
"""

import os
import re

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "github-schema-excerpt.graphql")
TOKEN = re.compile(r'"[^"]*"|\$?[A-Za-z_]\w*|\d+|[{}():!=,\[\]]')


def load_schema(path=SCHEMA_FILE):
    """Return {type name: {field name: (set of argument names, return type name)}}."""
    with open(path, encoding="utf-8") as handle:
        text = "\n".join(line for line in handle.read().split("\n") if not line.lstrip().startswith("#"))
    schema = {}
    for name, body in re.findall(r"(?:type|interface) (\w+) \{\n(.*?)\n\}", text, re.S):
        fields = {}
        for field, args, returns in re.findall(r"^\s+(\w+)(?:\(([^)]*)\))?: (\S+)$", body, re.M):
            fields[field] = (set(re.findall(r"(\w+):", args or "")), returns.strip("[]!"))
        schema[name] = fields
    return schema


def parse_query(query):
    """Return the top selection set as a list of (alias, name, {argument: value}, children)."""
    tokens = TOKEN.findall(query)
    pos = 0
    if tokens and tokens[0] == "query":
        pos = 1
        if tokens[pos] != "{" and tokens[pos] != "(":
            pos += 1  # operation name
        if tokens[pos] == "(":
            while tokens[pos] != ")":
                pos += 1
            pos += 1

    def selection(pos):
        assert tokens[pos] == "{", "expected { at token %d" % pos
        pos += 1
        fields = []
        while tokens[pos] != "}":
            alias = name = tokens[pos]
            pos += 1
            if tokens[pos] == ":":
                name = tokens[pos + 1]
                pos += 2
            args = {}
            if tokens[pos] == "(":
                pos += 1
                while tokens[pos] != ")":
                    if tokens[pos] == ",":
                        pos += 1
                        continue
                    assert tokens[pos + 1] == ":", "expected argument at token %d" % pos
                    args[tokens[pos]] = tokens[pos + 2]
                    pos += 3
                pos += 1
            children = []
            if tokens[pos] == "{":
                children, pos = selection(pos)
            fields.append((alias, name, args, children))
        return fields, pos + 1

    fields, _ = selection(pos)
    return fields


def check(query, schema=None):
    """Return a list of problems; empty when every field and argument exists."""
    schema = schema or load_schema()
    problems = []

    def walk(fields, type_name):
        known = schema.get(type_name)
        if known is None:
            problems.append("type %s is not in the schema excerpt" % type_name)
            return
        for _, name, args, children in fields:
            if name not in known:
                problems.append("Field '%s' doesn't exist on type '%s'" % (name, type_name))
                continue
            arg_names, returns = known[name]
            for arg in args:
                if arg not in arg_names:
                    problems.append("Field '%s' doesn't accept argument '%s'" % (name, arg))
            if children:
                walk(children, returns)
            elif returns in schema:
                problems.append("Field '%s' of type '%s' must have a selection of subfields" % (name, returns))

    walk(parse_query(query), "Query")
    return problems
