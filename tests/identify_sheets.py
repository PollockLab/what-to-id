"""Open and close the sheets and popovers holding Identify's controls, through their openers."""


def reveal(page, sel):
    """Open the sheet or popover holding sel through its visible opener, so sel can be clicked."""
    opener = page.evaluate(
        """s => { const h = document.querySelector(s).closest('dialog,[popover]');
        if (!h || h.matches('[open],:popover-open')) return null;
        return `[aria-controls="${h.id}"],[popovertarget="${h.id}"]`; }""",
        sel,
    )
    if opener:
        page.locator(opener).first.click()
    page.locator(sel).first.wait_for()


def close(page):
    """Close an open sheet, since a modal makes the cards inert."""
    page.keyboard.press("Escape")
    page.wait_for_function("!document.querySelector('dialog[open]')")
