from dataclasses import dataclass, field
from evaleval.hiccup import render


@dataclass(frozen=True)
class Selector:
    query: str


@dataclass(frozen=True)
class Eval:
    code: str


@dataclass(frozen=True)
class Action:
    name: str
    requires: str | None = field(default=None, compare=False, repr=False)


MORPH   = Action("MORPH",   requires="Selector")
PREPEND = Action("PREPEND", requires="Selector")
APPEND  = Action("APPEND",  requires="Selector")
REMOVE  = Action("REMOVE")
OUTER   = Action("OUTER",   requires="Selector")
CLASSES = Action("CLASSES", requires="Selector")
ADD     = Action("ADD",     requires="CLASSES")
TOGGLE  = Action("TOGGLE",  requires="CLASSES")


def _validate_step(items):
    item = items[-1]
    prior = items[:-1]

    prior_actions = [x for x in prior if isinstance(x, Action)]
    prior_action_names = {a.name for a in prior_actions}
    has_selector = any(isinstance(x, Selector) for x in prior)
    has_data = any(not isinstance(x, (Selector, Action, Eval)) for x in prior)

    if has_data:
        raise ValueError("Data must be the last item in the chain")

    match item:
        case Selector() if prior_actions:
            raise ValueError(f"Selector must come before actions, not after {prior_actions[-1].name}")
        case Action(name=name) if name in ("MORPH", "PREPEND", "APPEND", "OUTER", "CLASSES") and not has_selector:
            raise ValueError(f"{name} requires a Selector before it")
        case Action(name=name) if name in ("ADD", "TOGGLE") and "CLASSES" not in prior_action_names:
            raise ValueError(f"{name} requires CLASSES before it")
        case Action(name="REMOVE") if prior_actions and "CLASSES" not in prior_action_names:
            raise ValueError(f"Selector must come before actions, not after {prior_actions[-1].name}")


def _sel_expr(query):
    safe = query.replace("\\", "\\\\").replace('"', '\\"')
    return f'document.querySelector("{safe}")'


def _to_html(data):
    if data is None:
        return ""
    raw = render(data) if not isinstance(data, str) else data
    return raw.replace("`", "\\`").replace("${", "\\${")


def _compile(items):
    selector  = next((x for x in items if isinstance(x, Selector)), None)
    eval_node = next((x for x in items if isinstance(x, Eval)), None)
    actions   = [x for x in items if isinstance(x, Action)]
    data      = next((x for x in items if not isinstance(x, (Selector, Action, Eval))), None)

    lines = []
    ref = "null"

    if selector:
        ref = "_0"
        lines.append(f"const _0 = {_sel_expr(selector.query)}")

    if eval_node:
        code = eval_node.code
        if code.startswith("=>"):
            lines.append(code[2:].strip().replace("$", ref))
        else:
            lines.append(code)
        return ";\n".join(lines)

    html = _to_html(data)

    match tuple(a.name for a in actions):
        case ("REMOVE",):                  lines.append(f"{ref}?.remove()")
        case ("MORPH",):                   lines.append(f"Idiomorph.morph({ref}, `{html}`)")
        case ("PREPEND",):                 lines.append(f"{ref}.insertAdjacentHTML('afterbegin', `{html}`)")
        case ("APPEND",):                  lines.append(f"{ref}.insertAdjacentHTML('beforeend', `{html}`)")
        case ("OUTER",):                   lines.append(f"{ref}.outerHTML = `{html}`")
        case ("CLASSES", "ADD"):           lines.append(f"{ref}?.classList.add('{data}')")
        case ("CLASSES", "REMOVE"):        lines.append(f"{ref}?.classList.remove('{data}')")
        case ("CLASSES", "TOGGLE"):        lines.append(f"{ref}?.classList.toggle('{data}')")
        case _:                            lines.append("console.warn('unresolved patch chain')")

    return ";\n".join(lines)


class DepthChain:
    def __init__(self, depth, items=None):
        self.depth = depth
        self.items = items or []

    def __getitem__(self, item):
        items = self.items + [item]
        _validate_step(items)
        if len(items) >= self.depth:
            return _compile(items)
        return DepthChain(self.depth, items)

    def __str__(self):
        return _compile(self.items)


One   = DepthChain(1)
Two   = DepthChain(2)
Three = DepthChain(3)
Four  = DepthChain(4)
Five  = DepthChain(5)
Six   = DepthChain(6)
Seven = DepthChain(7)
Eight = DepthChain(8)
Nine  = DepthChain(9)
Ten   = DepthChain(10)
