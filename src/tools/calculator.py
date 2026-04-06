"""Safe calculator tool."""

from ..tool import tool


@tool
def calculator(expression: str) -> dict:
    """Evaluate a math expression safely. Supports +, -, *, /, **, %, parentheses.

    expression: The math expression to evaluate, e.g. "2 + 3 * 4"
    """
    # Whitelist safe characters
    allowed = set("0123456789+-*/().% ")
    cleaned = expression.replace("**", "^").replace("^", "**")

    if not all(c in allowed or c == '*' for c in cleaned):
        return {"error": f"Invalid characters in expression: {expression}"}

    try:
        result = eval(cleaned, {"__builtins__": {}}, {})
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}
