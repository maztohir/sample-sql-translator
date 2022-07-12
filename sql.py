#!/usr/bin/env python3
#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#


import argparse
import sys
import json

from sql_parser import parse
from sql_rewrite import convert, tables, tables_to_graph, MODES
from sql_refactor import Refactor

# Define command line arguments
argparser = argparse.ArgumentParser(description='Process SQL')
argparser.add_argument('--convert',
                       help='Convert', type=str, choices=MODES)
argparser.add_argument('--type',
                       default='format',
                       choices=['graph', 'tree', 'format'],
                       help='Output type')
argparser.add_argument('--graph_minimise',
                       help='Minimise the graph', action='store_true')
argparser.add_argument('--compact',
                       help='Compact formatted SQL', action='store_true')
argparser.add_argument('--output',
                       type=argparse.FileType('w'), nargs='?', default=sys.stdout,
                       help='SQL Output (default stdout)')
argparser.add_argument('sql_input',
                       type=argparse.FileType('r'), nargs='+', default=sys.stdin,
                       help='SQL Input')
argparser.add_argument('--refactor',
                       help='Refactor', action='store_true')
argparser.add_argument('--map_knowledge',
                       type=argparse.FileType('r'), nargs='+', default=sys.stdin,
                       help='Map Knowledge')

# Parse arguments
args = argparser.parse_args()

dep_tables = set()

for sql_input in args.sql_input:
    if args.refactor:
        knowledge = json.load(args.map_knowledge[0])
        refactor = Refactor(knowledge)
        refactor.refactor(sql_input.read())
        result = refactor.result()
        print(result)
        args.output.write(result)
        continue

    parsed = parse(sql_input.read())

    # Rewrite the query
    if args.convert:
        parsed = convert(args.convert, parsed)

    # Show the tables used (writing and reading)
    if args.type == 'graph':
        dep_tables.update(tables(parsed))

    # Show the get_tree() of the AST
    elif args.type == 'tree':
        args.output.write(parsed.get_tree())
        args.output.write('\n')

    # For the query
    elif args.type == 'format':
        sql = parsed.as_sql(args.compact)
        args.output.write(sql)
        args.output.write('\n')

# Graph of dependency is done on all of the SQL combined
if args.type == 'graph':
    min_graph = tables_to_graph(dep_tables, args.graph_minimise)

    args.output.write('digraph connections {\n')
    for dest in min_graph:
        for src in min_graph[dest]:
            args.output.write('"{}" -> "{}";\n'.format(dest, src))
    args.output.write('}\n')
