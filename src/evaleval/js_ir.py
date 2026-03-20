import json

from evaleval.adt import variant


class Expr:
    pass


class Stmt:
    pass


@variant
class Id(Expr):
    name: str


@variant
class Str(Expr):
    value: str


@variant
class RawExpr(Expr):
    code: str


@variant
class Member(Expr):
    obj: Expr
    prop: str
    optional: bool = False


@variant
class Call(Expr):
    callee: Expr
    args: tuple[Expr, ...] = ()


@variant
class Assign(Expr):
    left: Expr
    right: Expr


@variant
class And(Expr):
    left: Expr
    right: Expr


@variant
class Const(Stmt):
    name: str
    value: Expr


@variant
class ExprStmt(Stmt):
    expr: Expr


@variant
class If(Stmt):
    condition: Expr
    then: Stmt


@variant
class RawStmt(Stmt):
    code: str


@variant
class Program:
    statements: tuple[Stmt, ...]


def render_expr(expr: Expr) -> str:
    match expr:
        case Id(name):
            return name
        case Str(value):
            return json.dumps(value)
        case RawExpr(code):
            return code
        case Member(obj, prop, optional):
            op = "?." if optional else "."
            return f"{render_expr(obj)}{op}{prop}"
        case Call(callee, args):
            args_js = ", ".join(render_expr(arg) for arg in args)
            return f"{render_expr(callee)}({args_js})"
        case Assign(left, right):
            return f"{render_expr(left)} = {render_expr(right)}"
        case And(left, right):
            return f"{render_expr(left)} && {render_expr(right)}"
        case _:
            raise TypeError(f"Unsupported expression: {expr!r}")


def render_stmt(stmt: Stmt) -> str:
    match stmt:
        case Const(name, value):
            return f"const {name} = {render_expr(value)};"
        case ExprStmt(expr):
            return render_expr(expr)
        case If(condition, then):
            return f"if ({render_expr(condition)}) {render_stmt(then)}"
        case RawStmt(code):
            return code
        case _:
            raise TypeError(f"Unsupported statement: {stmt!r}")


def render_program(program: Program) -> str:
    return "\n".join(render_stmt(stmt) for stmt in program.statements)
