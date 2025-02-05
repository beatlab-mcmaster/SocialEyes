"""
textual_utils.py

Reference: https://github.com/Textualize/textual/discussions/3606
Edited by: Shreshth Saxena, Alexander Nguyen
Purpose: Utility functions for the main interface created with Textual python library.
"""


from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Iterable, Iterator
from textual.app import App

from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import CellDoesNotExist, RowKey
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer#, Checkbox
from textual.containers import HorizontalScroll


@dataclass
class Checkbox:
    """A checkbox, added to rows to make them selectable."""

    checked: bool = False

    def __str__(self) -> str:
        return "■" if self.checked else ""

    def __rich__(self) -> str:
        return "[b]■[/]" if self.checked else ""

    def check(self) -> None:
        """Uncheck the checkbox."""
        self.checked = True

    def uncheck(self) -> None:
        """Uncheck the checkbox."""
        self.checked = False

    def toggle(self) -> bool:
        """Toggle the checkbox."""
        self.checked = not self.checked
        return self.checked

@dataclass
class SelectableRow:
    """A selectable row."""

    table: SelectableRowsDataTable
    key: RowKey

    @property
    def app(self) -> App:
        """Textual application."""
        return self.table.app

    @property
    def _data(self) -> list:
        return self.table.get_row(self.key)

    @property
    def data(self) -> list:
        """Row data (without checkbox)."""
        return self._data[1:]

    @property
    def index(self) -> int:
        """Row index."""
        return self.table.get_row_index(self.key)

    @property
    def checkbox(self) -> Checkbox:
        """Row checkbox."""
        return self._data[0]

    def select(self) -> None:
        """Select this row."""
        self.checkbox.check()

    def unselect(self) -> None:
        """Unselect this row."""
        self.checkbox.uncheck()

    def toggle_select(self) -> bool:
        """Toggle-select this row."""
        return self.checkbox.toggle()

    @property
    def selected(self) -> bool:
        """Whether this row is selected."""
        return self.checkbox.checked

    def remove(self) -> None:
        """Remove row from the table."""
        self.table.remove_row(self.key)

    @property
    def previous(self):
        """Previous row (up)."""
        new_coord = Coordinate(self.index - 1, 0)
        key = self.table.coordinate_to_cell_key(new_coord).row_key
        return self.__class__(table=self.table, key=key)

    @property
    def next(self):  # noqa: A003
        """Next row (down)."""
        new_coord = Coordinate(self.index + 1, 0)
        key = self.table.coordinate_to_cell_key(new_coord).row_key
        return self.__class__(table=self.table, key=key)

class SelectableRowsDataTable(DataTable):
    """Data table with selectable rows."""
    

    ROW = SelectableRow
    BINDINGS: ClassVar = [
        Binding("space", "toggle_select_row", "Toggle select", show=False),
        Binding("ctrl+a, *", "toggle_select_all", "Toggle select all", show=False),
        Binding("exclamation_mark", "reverse_select", "Reverse select", show=False),
        Binding("shift+up", "toggle_select_up", "Expand select up", show=False),
        Binding("shift+down", "toggle_select_down", "Expand select down", show=False),
    ]

    # --------------------------------------------------
    # Textual methods.
    # --------------------------------------------------
    def add_rows(self, rows: Iterable[Iterable]) -> list[RowKey]:
        """Add rows.

        Automatically insert a column with checkboxes in position 0.
        """
        return super().add_rows((Checkbox("v"), *row) for row in rows)

    def clear(self, columns: bool = True):  # noqa: FBT001,FBT002
        """Clear rows and optionally columns.

        When clearing columns, automatically re-add a column for checkboxes.
        """
        super().clear(columns)
        if columns:
            self.add_column("", key="checkbox")
        return self

    # --------------------------------------------------
    # Binding actions.
    # --------------------------------------------------
    def action_toggle_select_row(self) -> None:
        """Toggle-select current row."""
        try:
            row = self.current_row
        except CellDoesNotExist:
            return
        row.toggle_select()
        self.force_refresh()

    def action_toggle_select_all(self) -> None:
        """Toggle-select all rows."""
        rows = list(self.selectable_rows)
        if all(row.selected for row in rows):
            for row in rows:
                row.unselect()
        else:
            for row in rows:
                row.select()
        self.force_refresh()

    def action_reverse_select(self) -> None:
        """Reverse selection."""
        for row in self.selectable_rows:
            row.toggle_select()
        self.force_refresh()

    def action_toggle_select_up(self) -> None:
        """Toggle selection up."""
        try:
            row = self.current_row
            previous_row = row.previous
        except CellDoesNotExist:
            pass
        else:
            previous_row.toggle_select()
            self.move_cursor(row=previous_row.index)
            self.force_refresh()

    def action_toggle_select_down(self) -> None:
        """Toggle selection down."""
        try:
            row = self.current_row
            next_row = row.next
        except CellDoesNotExist:
            pass
        else:
            next_row.toggle_select()
            self.move_cursor(row=next_row.index)
            self.force_refresh()

    # --------------------------------------------------
    # Additional methods/properties.
    # --------------------------------------------------
    def force_refresh(self) -> None:
        """Force refresh table."""
        # HACK: Without such increment, the table is refreshed
        # only when focus changes to another column.
        self._update_count += 1
        self.refresh()

    @property
    def current_row(self) -> SelectableRow:
        """Currently selected row."""
        key = self.coordinate_to_cell_key(self.cursor_coordinate).row_key
        return self.ROW(table=self, key=key)

    @property
    def selectable_rows(self) -> Iterator[SelectableRow]:
        """Rows, as selectable ones."""
        for key in self.rows:
            yield self.ROW(table=self, key=key)

    @property
    def selected_rows(self) -> Iterator[SelectableRow]:
        """Selected rows."""
        for row in self.selectable_rows:
            if row.selected:
                yield row


if __name__ == "__main__":
    app = TableApp()
    app.run()