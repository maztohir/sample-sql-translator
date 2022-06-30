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
from typing import Optional
from typing import List

from rfmt.blocks import LineBlock as LB
from rfmt.blocks import IndentBlock as IB
from rfmt.blocks import TextBlock as TB
from rfmt.blocks import StackBlock as SB
from rfmt.blocks import WrapBlock as WB
from .expr_op import SQLBiOp

from .utils import comments_sqlf

from .const import SQLString
from .ident import SQLIdentifier

from .node import SQLNode
from .node import SQLNodeList
from .expr import SQLExpr
from .types import SQLType
from .types import SQLNamedType


@dataclass(frozen=True)
class SQLFunction(SQLNode):
    name: SQLIdentifier
    params: SQLNodeList[SQLNode]
    retval: Optional[SQLNode]
    impl: SQLNode
    comments: List[str]
    options: Optional[SQLNodeList[SQLBiOp]]

    def sqlf(self, compact):

        # Start the stack with comments
        stack = comments_sqlf(self.comments)

        # Get params as a list of sqlf
        paramf = []
        if self.params and len(self.params):
            for param in self.params[:-1]:
                paramf.append(LB([param.sqlf(compact), TB(',')]))
            if self.params:
                paramf.append(self.params[-1].sqlf(compact))

            stack.append(LB([
                TB('CREATE TEMPORARY FUNCTION '),
                self.name.sqlf(True),
                TB('('),
                WB(paramf, sep=' '),
                TB(')')
            ]))
        else:
            stack.append(LB([
                TB('CREATE TEMPORARY FUNCTION '),
                self.name.sqlf(True),
                TB('()'),
            ]))

        if self.retval:
            stack.append(LB([TB('RETURNS '),
                             self.retval.sqlf(compact)]))

        if isinstance(self.impl, SQLString):
            optionf = []
            if self.options and len(self.options):
                optionf.append(TB('\nOPTIONS('))
                for option in self.options[:-1]:
                    optionf.append(LB([option.sqlf(compact), TB(',')]))
                optionf.append(self.options[-1].sqlf(compact))
                optionf.append(TB(')'))
            stack.append(TB('LANGUAGE js AS'))
            if len(optionf):
                stack.append(IB(LB([
                    self.impl.sqlf(compact), WB(optionf, sep=' '),
                    TB(';')
                ])))
            else:
                stack.append(IB(LB([
                    self.impl.sqlf(compact),
                    TB(';')
                ])))
        else:
            stack.append(TB('AS'))
            stack.append(IB(LB([self.impl.sqlf(compact),
                                TB(';')])))
        stack.append(TB(''))

        return SB(stack)

    @staticmethod
    def consume(lex) -> 'Optional[SQLFunction]':
        if not (lex.consume(['CREATE', 'TEMP', 'FUNCTION']) or
                lex.consume(['CREATE', 'TEMPORARY', 'FUNCTION'])):
            return None

        comments = lex.get_comments()

        name = (SQLIdentifier.consume(lex) or
                lex.error('Expected UDF name'))

        lex.expect('(')
        params = []
        options = []
        if not lex.consume(')'):
            while True:
                var_name = SQLIdentifier.parse(lex)
                ltype = SQLType.parse(lex)
                params.append(SQLNamedType(var_name, ltype))
                if not lex.consume(','):
                    break
            lex.expect(')')

        rtype = None

        # Javascript function
        if lex.consume('RETURNS'):
            rtype = SQLType.parse(lex)
            lex.expect('LANGUAGE')
            lex.expect('JS')
            lex.expect('AS')
            impl = (SQLString.consume(lex, quotechar='"""') or
                    lex.error('Expected Javascript code'))
            if lex.consume('OPTIONS'):
                lex.expect('(')
                while True:
                    var = SQLIdentifier(lex.consume_identifier())
                    lex.consume('=')
                    val = SQLString(lex.consume_string()[0])
                    options.append(SQLBiOp('=', var, val))
                    if lex.consume(')'):
                        break
                    lex.consume(',')
        # SQL-expression
        else:
            lex.expect('AS')
            impl = SQLExpr.parse(lex)

        comments.extend(lex.get_comments())

        return SQLFunction(name, SQLNodeList(params),
                           rtype, impl, comments, SQLNodeList(options))
