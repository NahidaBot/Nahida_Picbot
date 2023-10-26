"""
转义标题、描述等字符串，防止与 telegram markdown_v2 或 telegram html 符号冲突
"""


def md_esc(markdownv2_str: str) -> str:
    """
    Telegram 的 Markdown 格式，只有 v2 才支持元素嵌套，同时需要在正文中对以下字符进行额外的转义。
    详见：https://core.telegram.org/bots/api#formatting-options
    """
    chars = "_*[]()~`>#+-=|{}.!"
    for char in chars:
        markdownv2_str = markdownv2_str.replace(char, "\\" + char)
    return markdownv2_str


def html_esc(html_str: str) -> str:
    return html_str.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
