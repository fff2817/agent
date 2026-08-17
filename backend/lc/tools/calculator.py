"""
calculator 工具 — 执行安全的数学表达式计算。

使用 LangChain @tool，供 Agent Function Calling / bind_tools 自动调用。
"""

from __future__ import annotations

import ast
import logging
import operator

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    """递归求值 AST 节点，只允许数字和四则运算。"""
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


def _calculate(expression: str) -> str:
    """计算器核心逻辑；返回结果字符串或 Error: ..."""
    logger.info("[Tool] 收到计算请求, expression=%r", expression)

    expression = expression.strip()
    if not expression:
        logger.warning("[Tool] 表达式为空")
        return "Error: expression is empty"

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)

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


@tool
def calculator(expression: str) -> str:
    """执行数学计算。当用户问数学运算、需要精确数字结果时使用此工具。支持 +、-、*、/ 和括号，例如 '123 * 456'。

    Args:
        expression: 要计算的数学表达式，例如 '123 * 456'
    """
    return _calculate(expression)


# 兼容旧调用名
def run_calculator(expression: str) -> str:
    return calculator.invoke({"expression": expression})
