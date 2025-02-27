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

from dataclasses import dataclass
from typing import List
from typing import Optional

from rfmt.blocks import ChoiceBlock as CB
from rfmt.blocks import IndentBlock as IB
from rfmt.blocks import LineBlock as LB
from rfmt.blocks import StackBlock as SB
from rfmt.blocks import TextBlock as TB
from rfmt.blocks import WrapBlock as WB

from .utils import with_commas

from .query import SQLQuery
from .query_impl import SQLOrderLimitOffset
from .expr import SQLExpr
from .const import SQLConstant
from .const import SQLNumber
from .ident import SQLIdentifierPath
from .node import SQLNode
from .node import SQLNodeList
from .expr_funcs import SQLFuncExpr, SQLCustomFuncs
from .types import SQLStruct, SQLType
from .expr_op import SQLStruct as SQLStructOp

@dataclass(frozen=True)
class SQLArrayLiteral(SQLExpr):
    args: SQLNodeList
    type: Optional[SQLType]

    def sqlf(self, compact):
        if not self.type:
            compact_sql = LB([
                TB('['),
                LB(with_commas(True, self.args)),
                TB(']')
            ])
            if compact:
                return compact_sql
            return CB([
                compact_sql,
                LB([
                    TB('['),
                    WB(with_commas(compact, self.args, tail=']'))
                ]),
            ])
        else:
            start_arg_parenthesis = '['
            end_arg_parenthesis = ']'
            compact_sql = LB([
                TB('ARRAY<'),
                self.type.sqlf(compact=False),
                TB('>'),
                TB(start_arg_parenthesis),
                LB(with_commas(True, self.args)),
                TB(end_arg_parenthesis)
            ])
            if compact:
                return compact_sql
            return CB([
                SB([
                    LB([TB('ARRAY<'),
                    self.type.sqlf(compact=False),
                    TB('>')]),
                WB([TB(start_arg_parenthesis)] +
                    with_commas(compact, self.args, tail=end_arg_parenthesis))
                ]),
            ])

    @staticmethod
    def consume(lex) -> 'Optional[SQLArrayLiteral]':
        type : SQLType = None
        if lex.consume(['ARRAY', '<']):
            type = SQLType.consume(lex)
            lex.consume('>')
        if not lex.consume_any([['ARRAY', '['],'[']):
            return None
        exprs: List[SQLExpr] = []
        while True:
            exprs.append(SQLExpr.parse(lex))
            if not lex.consume(','):
                break
        lex.expect(']')
        return SQLArrayLiteral(SQLNodeList(exprs), type)

@dataclass(frozen=True)
class SQLArraySelect(SQLExpr):
    query: SQLQuery

    def sqlf(self, compact):
        compact_sql = LB([
            TB('ARRAY('), self.query.sqlf(True), TB(')')
        ])

        if compact:
            return compact_sql

        return CB([
            compact_sql,
            SB([
                TB('ARRAY('),
                IB(self.query.sqlf(compact)),
                TB(')')
            ])
        ])

    @staticmethod
    def consume(lex) -> 'Optional[SQLArraySelect]':
        if not lex.consume('ARRAY'):
            return None

        lex.expect('(')
        query = SQLQuery.parse(lex)
        lex.expect(')')
        return SQLArraySelect(query)


@dataclass(frozen=True)
class SQLArrayAgg(SQLExpr):
    is_distinct: bool
    expr: SQLNodeList
    type: Optional[SQLType]
    nulls: Optional[str]
    order_limit_offset: Optional[SQLOrderLimitOffset]
    analytic: Optional[SQLNode]
    offset: Optional[int]

    def sqlf(self, compact):
        lines = [TB('ARRAY_AGG(')]
        if self.type:
            lines.append(self.type.sqlf(compact))
        if self.is_distinct:
            lines.append(TB('DISTINCT '))
        lines.append(self.expr.sqlf(True))
        if self.nulls:
            lines.append(TB(self.nulls) + ' NULLS')
        if self.order_limit_offset:
            lines.append(self.order_limit_offset.sqlf(True))
        if self.analytic:
            lines.append(self.analytic.sqlf(True))
        lines.append(TB(')'))
        if self.offset:
            lines.append(TB('[OFFSET('))
            lines.append(TB(' ') )
            lines.append(self.offset.sqlf(compact))
            lines.append(TB(')]'))

        compact_sql = LB(lines)

        if compact:
            return compact_sql

        stack = [TB('ARRAY_AGG(')]
        if self.type:
            stack.append(self.type.sqlf(compact))
        indent = []
        if self.is_distinct:
            indent.append(
                LB([TB('DISTINCT '), self.expr.sqlf(compact)]))
        else:
            indent.append(self.expr.sqlf(compact))
        if self.nulls:
            indent.append(TB(self.nulls) + ' NULLS')
        if self.order_limit_offset:
            indent.append(self.order_limit_offset.sqlf(compact))
        if self.analytic:
            indent.append(self.analytic.sqlf(compact))
        stack.append(IB(SB(indent)))
        stack.append(TB(')'))
        if self.offset:
            stack.append(TB('[OFFSET('))
            stack.append(TB(' ') )
            stack.append(self.offset.sqlf(compact))
            stack.append(TB(')]'))

        return CB([
            compact_sql,
            SB(stack)
        ])

    @staticmethod
    def consume(lex) -> 'Optional[SQLArrayAgg]':
        if not lex.consume(['ARRAY_AGG', '(']):
            return None

        type : SQLType = None
        is_distinct = False
        nulls = None
        order_limit_offset = None
        analytic = None

            
        expr = SQLCustomFuncs.consume(lex)
        if not expr and lex.peek('STRUCT'):
            type = SQLStruct.consume(lex)
            lex.expect('(')
            exprs : List[SQLExpr] = []
            while True:
                exprs.append(SQLExpr.parse(lex))
                if lex.consume(')'):
                    break
                lex.expect(',')
            expr = SQLStructOp(SQLNodeList(exprs))
        elif not expr:
            is_distinct = bool(lex.consume('DISTINCT'))

            expr = SQLExpr.parse(lex)

            nulls = None
            if lex.consume('IGNORE'):
                nulls = 'IGNORE'
                lex.expect('NULLS')
            elif lex.consume('RESPECT'):
                nulls = 'RESPECT'
                lex.expect('NULLS')

            order_limit_offset = SQLOrderLimitOffset.consume(lex)

            analytic = SQLAnalytic.consume(lex)
        lex.expect(')')

        offset = None
        if lex.consume('['):
            lex.expect('OFFSET')
            lex.consume('(')
            offset = SQLNumber.parse(lex)
            lex.consume(')')
            lex.expect(']')

        return SQLArrayAgg(is_distinct, expr, type, nulls,
                           order_limit_offset, analytic, offset)


@dataclass(frozen=True)
class SQLStringAgg(SQLExpr):
    name: str
    is_distinct: bool
    expr: SQLNode
    delimiter: Optional[str]
    nulls: Optional[str]
    order_limit_offset: Optional[SQLOrderLimitOffset]
    analytic: Optional[SQLNode]
    analytic_name: Optional[str]
    number: Optional[int]

    def sqlf(self, compact):
        lines = [TB('{}('.format(self.name))]
        if self.is_distinct:
            lines.append(TB('DISTINCT '))
        lines.append(self.expr.sqlf(True))
        if self.delimiter:
            lines.append(TB(', '+ self.delimiter.as_sql(compact)))
        if self.nulls:
            lines.append(TB(self.nulls) + ' NULLS')
        if self.order_limit_offset:
            lines.append(self.order_limit_offset.sqlf(True))
        if self.analytic:
            lines.append(self.analytic.sqlf(True))
        lines.append(TB(')'))
        if self.number:
            if self.analytic_name:
                lines.append(TB('[{}('.format(self.analytic_name)))
                lines.append(TB(' ') )
                lines.append(self.number.sqlf(compact))
                lines.append(TB(')]'))
            else:
                lines.append(TB('['))
                lines.append(self.number.sqlf(compact))
                lines.append(TB(']'))

        compact_sql = LB(lines)

        if compact:
            return compact_sql

        stack = [TB('{}('.format(self.name))]
        indent = []
        if self.is_distinct:
            args = [TB('DISTINCT '), self.expr.sqlf(compact)]
        else:
            args = [self.expr.sqlf(compact)]
        if self.delimiter:
            args.append(TB(', ' + self.delimiter.as_sql(compact)))
        indent.append(LB(args))
        
        if self.nulls:
            indent.append(TB(self.nulls) + ' NULLS')
        if self.order_limit_offset:
            indent.append(self.order_limit_offset.sqlf(compact))
        if self.analytic:
            indent.append(self.analytic.sqlf(compact))
        stack.append(IB(SB(indent)))
        stack.append(TB(')'))
        if self.number:
            if self.analytic_name:
                stack.append(TB('[{}('.format(self.analytic_name)))
                stack.append(TB(' ') )
                stack.append(self.number.sqlf(compact))
                stack.append(TB(')]'))
            else:
                stack.append(TB('['))
                stack.append(self.number.sqlf(compact))
                stack.append(TB(']'))

        return CB([
            compact_sql,
            SB(stack)
        ])

    @staticmethod
    def consume(lex) -> 'Optional[SQLStringAgg]':
        function_consumed = lex.consume(['STRING_AGG', '(']) or lex.consume(['SPLIT', '('])
        if not function_consumed:
            return None

        name = function_consumed[0]
        is_distinct = bool(lex.consume('DISTINCT'))

        expr = SQLExpr.parse(lex)
        delimiter = None

        if lex.consume(','):
            delimiter = SQLConstant.consume(lex)

        nulls = None
        if lex.consume('IGNORE'):
            nulls = 'IGNORE'
            lex.expect('NULLS')
        elif lex.consume('RESPECT'):
            nulls = 'RESPECT'
            lex.expect('NULLS')

        order_limit_offset = SQLOrderLimitOffset.consume(lex)

        analytic = SQLAnalytic.consume(lex)

        lex.expect(')')

        analytic_name = None
        number = None
        if lex.consume('['):
            analytic_name = SQLConstant.consume(lex)
            lex.consume('(')
            number = SQLNumber.parse(lex)
            lex.consume(')')
            lex.expect(']')

        return SQLStringAgg(name, is_distinct, expr, delimiter, nulls,
                           order_limit_offset, analytic, analytic_name, number)


@dataclass(frozen=True)
class SQLExprWithAnalytic(SQLExpr):
    function: SQLExpr
    analytic: SQLNode

    def sqlf(self, compact):
        compact_sqlf = LB([self.function.sqlf(compact), TB(' '),
                           self.analytic.sqlf(compact)])
        if compact:
            return compact_sqlf

        return CB([
            compact_sqlf,
            SB([self.function.sqlf(compact),
                self.analytic.sqlf(compact)])
        ])

    @staticmethod
    def parse(lex) -> 'SQLExpr':

        # Try alternatives first
        expr: SQLExpr = (SQLConstant.consume(lex) or
                         SQLArrayLiteral.consume(lex) or
                         SQLArrayAgg.consume(lex) or
                         SQLStringAgg.consume(lex) or
                         SQLArraySelect.consume(lex) or
                         SQLCustomFuncs.consume(lex) or
                         SQLIdentifierPath.parse(lex))

        # If it is a SQLIdentifierPath, it may be
        # a normal function call.
        if isinstance(expr, SQLIdentifierPath) and lex.consume('('):

            # Parse as a function
            func_args: List[SQLExpr] = []
            if not lex.consume(')'):
                while True:
                    func_args.append(SQLExpr.parse(lex))
                    if not lex.consume(','):
                        break
                lex.expect(')')

            # Turn it into a function
            expr = SQLFuncExpr(expr.names, SQLNodeList(func_args))
        elif isinstance(expr, SQLIdentifierPath) and len(expr.names)==1 and expr.names[0].value.upper() == 'DATE' and (lex.peek('\'') or lex.peek('"')):
            func_args = [SQLExpr.parse(lex)]
            expr = SQLFuncExpr(expr.names, SQLNodeList(func_args))

        window = SQLAnalytic.consume(lex)
        if window:
            expr = SQLExprWithAnalytic(expr, window)

        return expr


@dataclass(frozen=True)
class SQLAnalytic(SQLExpr):
    partition_by: SQLNodeList
    order_by: SQLNodeList
    range_desc: str

    def sqlf(self, compact):
        lines = []
        lines.append(TB('OVER ('))
        if self.partition_by:
            lines.append(TB('PARTITION BY '))
            lines.extend(with_commas(True, self.partition_by, ','))
        if self.order_by:
            lines.append(TB(' ORDER BY '))
            lines.extend(with_commas(True, self.order_by, ','))
        if self.range_desc:
            lines.append(TB(self.range_desc))
        lines.append(TB(')'))

        if compact:
            return LB(lines)

        full_sql = [
            TB('OVER ('),
        ]
        if self.partition_by:
            full_sql.append(
                IB(
                    SB([
                        TB('PARTITION BY'), IB(
                            WB(with_commas(True, self.partition_by)))
                    ])))
        if self.order_by:
            full_sql.append(
                IB(
                    SB([
                        TB('ORDER BY'), IB(
                            WB(with_commas(True, self.order_by)))
                    ])))
        if self.range_desc:
            full_sql.append(IB(TB(self.range_desc)))
        full_sql.append(TB(')'))

        r = CB([LB(lines), SB(full_sql)])
        return r

    @staticmethod
    def consume(lex) -> 'Optional[SQLAnalytic]':
        if not lex.consume('OVER'):
            return None

        lex.expect('(')

        partition_by = []
        if lex.consume('PARTITION'):
            lex.expect('BY')
            while True:
                partition_by.append(SQLExpr.parse(lex))
                if not lex.consume(','):
                    break

        order_by = []
        if lex.consume('ORDER'):
            lex.expect('BY')
            while True:
                oby = SQLExpr.parse(lex)
                order = None
                if lex.consume('ASC'):
                    order = 'ASC'
                elif lex.consume('DESC'):
                    order = 'DESC'
                # TODO(scannell): Capture ASC/DESC
                order_by.append(oby)
                if not lex.consume(','):
                    break

        win_spec = (lex.consume('ROWS') or lex.consume('RANGE'))

        # If window specified, parse it out
        if win_spec:
            if lex.consume('BETWEEN'):
                win_spec += (' BETWEEN ' +
                             SQLAnalytic._parse_frame_boundary(lex))
                lex.expect('AND')
                win_spec += ' AND ' + SQLAnalytic._parse_frame_boundary(lex)
            else:
                win_spec += ' ' + SQLAnalytic._parse_frame_boundary(lex)

        lex.expect(')')

        # Return analytics function
        return SQLAnalytic(SQLNodeList(partition_by),
                           SQLNodeList(order_by),
                           win_spec)

    @staticmethod
    def _parse_frame_boundary(lex):
        if lex.consume('UNBOUNDED'):
            typ = lex.consume('PRECEDING') or lex.consume('FOLLOWING') or lex.error('Expected PRECEDING or FOLLOWING')
            return 'UNBOUNDED {}'.format(typ)

        if lex.consume('CURRENT'):
            lex.expect('ROW')
            return 'CURRENT ROW'

        num = SQLNumber.consume(lex)

        num_typ = (lex.consume('PRECEDING') or lex.consume('FOLLOWING') or
                   lex.error('Expected PRECEDING or FOLLOWING'))

        return '{} {}'.format(num, num_typ)
