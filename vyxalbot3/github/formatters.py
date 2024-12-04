import re


def escape_markdown(text: str) -> str:
    return re.sub(f"([{re.escape("_*`[]")}])", r"\\\1", text)


def user_link(user: dict) -> str:
    return f'[{escape_markdown(user["login"])}]({user["html_url"]})'


def repository_link(repo: dict, fullName: bool = True) -> str:
    return f'[{escape_markdown(repo["full_name"] if fullName else repo["name"])}]({repo["html_url"]})'


def issue_link(issue: dict) -> str:
    return f'[#{issue["number"]}]({issue["html_url"]}) ({issue["title"]})'


def ref_link(ref: str, repo: dict) -> str:
    return f'[{repo["name"]}/{ref}]({repo["html_url"]}/tree/{ref})'
