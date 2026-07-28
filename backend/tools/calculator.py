"""
calculator 工具 — 执行安全的数学表达式计算。

LLM 不擅长大数精确运算，遇到 "123 * 456" 这类问题时
应调用此工具，由 Python 算出准确结果。
"""

import ast
import logging
import operator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 给 LLM 看的工具说明书（OpenAI Function Calling 格式）
# LLM 读这份 schema 来决定：什么时候调、传什么参数
# ---------------------------------------------------------------------------
CALCULATOR_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": (
            "执行数学计算。当用户问数学运算、需要精确数字结果时使用此工具。"
            "支持 +、-、*、/ 和括号，例如 '123 * 456'。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式，例如 '123 * 456'",
                }
            },
            "required": ["expression"],
        },
    },
}

# 允许 AST 节点使用的运算符映射（白名单，防止执行任意代码）
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    """
    递归求值 AST 节点，只允许数字和四则运算。

    参数:
        node: Python ast 模块解析出的语法树节点

    返回:
        计算结果的数值

    异常:
        ValueError: 表达式包含不允许的语法（如函数调用、变量名）
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)

    raise ValueError(f"不允许的表达式类型: {type(node).__name__}")


def run_calculator(expression: str) -> str:
    """
    计算器工具的执行入口（Handler）。

    由 registry 调用，Agent 不直接调用此函数。

    参数:
        expression: 数学表达式字符串，如 "123 * 456"

    返回:
        计算结果的字符串；出错时返回 "Error: ..." 格式的错误信息
    """
    logger.info("[Tool] 收到计算请求, expression=%r", expression)

    expression = expression.strip()
    if not expression:
        logger.warning("[Tool] 表达式为空")
        return "Error: expression is empty"

    try:
        # 用 ast 解析而非 eval()，只允许白名单内的运算
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)

        # 整数结果去掉小数点（56088.0 → "56088"）
        if isinstance(result, float) and result.is_integer():
            result_str = str(int(result))
        else:
            result_str = str(result)

        logger.info("[Tool] 计算完成, 结果=%s", result_str)
        return result_str

    except ZeroDivisionError:
        logger.warning("[Tool] 除零错误, expression=%r", expression)
        return "Error: division by zero"
    except (SyntaxError, ValueError) as exc:
        logger.warning("[Tool] 表达式无效, expression=%r, error=%s", expression, exc)
        return f"Error: invalid expression — {exc}"
