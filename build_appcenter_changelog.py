#!/usr/bin/env python3

import subprocess

from lxml import html


def extract_changelog_section():
    with open("_build/html/changelog.html", "r") as f:
        content = f.read()
    tree = html.fromstring(content)
    section = tree.xpath('//*[@id="changelog"]')

    if section:
        # Convert the first match back to a string
        return html.tostring(section[0], encoding="unicode", pretty_print=True)
    raise ValueError("No changelog section found!")


def wrap_changelog(changelog):
    html = "<div>\n" f"{changelog}\n" "</div>"
    return html


def main():
    subprocess.check_call(
        [
            "sphinx-build",
            "--define",
            "html_theme_options.univention_matomo_tracking=False",
            "--define",
            "univention_feedback=0",
            "--builder",
            "html",
            "doc/docs/",
            "_build/html/",
        ]
    )
    changelog = wrap_changelog(extract_changelog_section())
    with open("changelog.html", "w") as f:
        f.write(changelog)


if __name__ == "__main__":
    main()
