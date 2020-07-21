import html

from ipysheet import column, hold_cells, sheet  # type: ignore
from ipywidgets import (
    BoundedIntText,
    Button,
    HBox,
    HTML,
    Label,
    Layout,
    Select,
    Tab,
    Text,
    VBox,
)  # type: ignore

from math import ceil  # type:ignore

from neurolang.datalog.wrapped_collections import (
    WrappedRelationalAlgebraSet,
)  # type: ignore

from neurolang_ipywidgets import NlCodeEditor, NlDownloadLink, NlIconTab
from nlweb.viewers.factory import ColumnsManager

# This should be changed when neurolang gets
# a unified exceptions hierarchy
from tatsu.exceptions import FailedParse

from traitlets import Int, Unicode  # type: ignore

from typing import Dict, Optional


class PaginationWidget(HBox):
    """A pagination widget that enables setting page number and the number of rows per page.
    """

    # number of rows in a page by default
    DEFAULT_LIMIT = 50
    # max number of rows to avoid performance problems
    MAX_LIMIT = 100

    # current page number
    page = Int()
    # number of rows per page.
    limit = Int()

    def __init__(self, nb_rows, limit=50, *args, **kwargs):
        """
        Parameters
        ----------
        nb_rows: int
            total number of rows in the result set.
        limit: int
            number of rows to display in a page.

        """
        super().__init__(*args, **kwargs)

        self.__nb_rows = nb_rows if nb_rows else 1
        self.page = 1
        self.limit = (
            limit
            if limit and limit > 0 and limit < PaginationWidget.MAX_LIMIT
            else PaginationWidget.DEFAULT_LIMIT
        )

        self.layout.width = "400px"

        if nb_rows > limit:
            self.layout.visibility = "visible"
        else:
            self.layout.visibility = "hidden"

        nb_pages = self._get_nb_pages(self.limit)

        # widget to set page number
        self.__page_widget = BoundedIntText(
            value=self.page,
            min=1,
            max=nb_pages,
            step=1,
            description="page",
            description_tooltip="Current page",
            disabled=False,
            style={"description_width": "30px"},
            layout=Layout(width="90px", max_width="90px"),
        )

        # widget to display total number of pages.
        self.__label_slash = Label(value=f"/ {nb_pages}", layout=Layout(width="60px"))

        # widget to set limit
        self.__limit_widget = BoundedIntText(
            value=self.limit,
            min=1,
            max=PaginationWidget.MAX_LIMIT,
            step=1,
            description="rows",
            description_tooltip=f"Number of rows per page. Max. possible: {PaginationWidget.MAX_LIMIT}",
            disabled=False,
            style={"description_width": "30px"},
            layout=Layout(width="90px", max_width="90px"),
        )

        self.__page_widget.observe(self._page_widget_changed, names="value")
        self.__limit_widget.observe(self._limit_widget_changed, names="value")

        self.children = [self.__page_widget, self.__label_slash, self.__limit_widget]

    def _get_nb_pages(self, limit):
        return ceil(self.__nb_rows / self.limit)

    def _page_widget_changed(self, change):
        self.page = change.new

    def _limit_widget_changed(self, change):
        new_limit = change.new
        # update limit
        self.limit = new_limit
        self.page = 1

        nb_pages = self._get_nb_pages(new_limit)

        # update page widget
        self.__page_widget.max = nb_pages
        self.__page_widget.value = 1

        # update label slash widget
        self.__label_slash.value = f"/ {nb_pages}"


class ResultTabPageWidget(VBox):
    """Tab page widget that displays result table and controls for each column type in the result table.."""

    icon = Unicode()

    DOWNLOAD_THRESHOLD = 500000

    def __init__(
        self, title: str, wras: WrappedRelationalAlgebraSet, cheaders, *args, **kwargs
    ):
        """

        Parameters
        ----------
        title: str
            title for the tab page.
        wras: WrappedRelationalAlgebraSet
            query result for the specified `title`.
        cheaders: list
            column header list for result table.
        """
        super().__init__(*args, **kwargs)
        self.loaded = False
        self._df = wras.as_pandas_dataframe()
        self._title = title
        self._total_nb_rows = self._df.shape[0]
        self._nb_cols = wras.arity
        self._cheaders = cheaders

        # initialize columns manager that generates widgets for each column, column viewers, and controls
        self._columns_manager = ColumnsManager(self, wras.row_type)

        self._cell_viewers = self._columns_manager.get_viewers()
        self._controls = self._columns_manager.get_controls()

        self._create_title()

    def _create_title(self):
        # initialize widgets
        # set tab page title
        title_label = HTML(
            f"<h3>{self._title}</h3>", layout=Layout(padding="0px 5px 5px 0px")
        )

        self._hbox_title = HBox(
            layout=Layout(justify_content="space-between", align_items="center")
        )

        # create download link
        dw = NlDownloadLink(
            layout=Layout(
                width="30px",
                max_width="30px",
                min_width="30px",
                margin="5px 5px 5px 0",
                padding="0 0 0 0",
                flex="0 1 0",
                align_self="center",
            )
        )

        hbox_table_info = HBox(
            [title_label, dw],
            layout=Layout(justify_content="flex-start", align_items="center"),
        )

        # add paginator if there exist no ExplicitVBR or ExplicitVBROverlay column
        if not self._columns_manager.hasVBRColumn:

            if self._total_nb_rows <= ResultTabPageWidget.DOWNLOAD_THRESHOLD:
                dw.filename = f"{self._title}.csv"
                dw.tooltip = f"Download {dw.filename} file."

                def clicked(event):
                    dw.content = self._df.to_csv(index=False).encode()

                dw.on_click(clicked)
            else:
                dw.disabled = True
                dw.tooltip = "Not available for download due to size!"

            paginator = PaginationWidget(
                self._df.shape[0], layout=Layout(padding="0px 0px 0px 50px")
            )
            self._limit = paginator.limit
            paginator.observe(self._page_number_changed, names="page")
            paginator.observe(self._limit_changed, names="limit")

            hbox_table_info.children = hbox_table_info.children + (paginator,)
        else:
            dw.tooltip = "Not available for download due to column type!"
            dw.disabled = True

            self._limit = self._total_nb_rows

        if self._controls is not None:
            hbox_menu = HBox(self._controls)
            self._hbox_title.children = [hbox_table_info, hbox_menu]

    def load(self):
        if not self.loaded:
            self.loaded = True

            self._load_table(1, self._limit)

            self.children = [self._hbox_title, self._table]

    def _page_number_changed(self, change):
        self._load_table(change.new, self._limit)
        self.children = [self.children[0], self._table]

    def _limit_changed(self, change):
        print("called limit changed")
        self._limit = change.new
        self._load_table(1, self._limit)
        self.children = [self.children[0], self._table]

    def _load_table(self, page, limit):
        """
        Parameters
        ----------
        page: int
            page number to view.
        limit: int
            number of rows to display.
        """
        self._table = sheet(
            rows=min(self._total_nb_rows, self._limit),
            columns=self._nb_cols,
            column_headers=self._cheaders,
            layout=Layout(width="auto", height="330px"),
        )

        start = (page - 1) * limit
        end = min(start + limit, len(self._df))

        with hold_cells():
            for col_index, column_id in enumerate(self._df.columns):
                column_data = self._df[column_id]
                column_feeder = self._columns_manager.get_column_feeder(col_index)
                rows = []

                for row_index in range(start, end):
                    rows.append(column_feeder.get_widget(column_data[row_index]))
                    column(col_index, rows, row_start=0)

    def get_viewers(self):
        """Returns list of viewers for this tab page.

        list
            list of cell viewers for this tab page.
        """
        return self._cell_viewers


class QResultWidget(VBox):
    """A widget to display query results and corresponding viewers."""

    def __init__(self):
        super().__init__()
        # tab widget that displays each resultset in an individual tab
        self._tab = NlIconTab(layout=Layout(height="460px"))
        # viewers necessary for each resultset, can be shared among resultsets
        self._viewers = None

    def _create_result_tabs(
        self, res: Dict[str, WrappedRelationalAlgebraSet], pnames: Dict
    ):
        """Creates necessary tab pages and viewers for the specified query result `res`.

        Parameters
        ----------
        res: Dict[str, WrappedRelationalAlgebraSet]
           dictionary of query results with keys as result name and values as result for corresponding key.
        pnames: Dict[str, tuple]
           dictionary of query result column names with keys as result name and values as tuple of column names for corresponding key.

        Returns
        -------
        result_tabs: list
            list of tab pages to be added to tab as children.
        titles: list
            list of titles for tab pages.
        icons: list
            list of icons for tab pages.
        viewers: set
            set of viewers for all tab pages.
        """
        result_tabs = []
        titles = []
        icons = []

        # set of all viewers for each result_tab
        viewers = set()

        def icon_changed(change):
            icons = []

            for result_tab in result_tabs:
                icons.append(result_tab.icon)
            self._tab.title_icons = icons

        for name in sorted(res.keys()):
            result_set = res[name]
            result_tab = ResultTabPageWidget(
                name, result_set, list(pnames[name]), layout=Layout(height="100%")
            )

            result_tabs.append(result_tab)
            titles.append(name)
            icons.append(result_tab.icon)

            result_tab.observe(icon_changed, names="icon")

            viewers = viewers | result_tab.get_viewers()

        return result_tabs, titles, icons, viewers

    def _tab_index_changed(self, change):
        tab_page = self._tab.children[self._tab.selected_index]

        if not tab_page.loaded:
            tab_page.load()

    def show_results(self, res: Dict[str, WrappedRelationalAlgebraSet], pnames: Dict):
        """Creates and displays necessary tab pages and viewers for the specified query result `res`.

        Parameters
        ----------
        res: Dict[str, WrappedRelationalAlgebraSet]
           dictionary of query results with keys as result name and values as result for corresponding key.
        pnames: Dict[str, tuple]
           dictionary of query result column names with keys as result name and values as tuple of column names for corresponding key.
        """
        self.reset()

        result_tabs, titles, icons, self._viewers = self._create_result_tabs(
            res, pnames
        )

        self._tab.children = result_tabs

        for i, title in enumerate(titles):
            self._tab.set_title(i, title)

        self._tab.title_icons = icons

        # observe to load each table upon tab selection
        self._tab.observe(self._tab_index_changed, names="selected_index")

        self._tab.selected_index = 0
        self._tab_index_changed(None)

        self.children = (self._tab,) + tuple(self._viewers)

    def reset(self):
        """Resets this query result widget removing all tabs in tab widget and resetting and removing all viewers."""
        if self._viewers is not None:
            for viewer in self._viewers:
                viewer.reset()
        self._viewers = None

        self._tab.reset()


class SymbolsWidget(HBox):
    """
    A list of symbols, plus a filtering search box
    """

    def __init__(self, nl, **kwargs):
        self.nl = nl
        self.list = Select(options=self.nl.symbols)
        self.search_box = Text(placeholder="search")
        self.help = HTML()
        super().__init__(**kwargs)

        self.children = [VBox([self.search_box, self.list]), self.help]

        self.help.layout = Layout(flex="1 1 65%")

        self.list.observe(self.on_select_change, names="value")
        self.on_select_change(None)

        self.search_box.observe(self.on_search_change, names="value")

    def on_select_change(self, change):
        help = self.nl.symbols[self.list.value].help()
        self.help.value = _format_help_message(self.list.value, help)

    def on_search_change(self, change):
        if self.search_box.value == "":
            self.list.options = self.nl.symbols
        else:
            filtered_options = [
                item for item in self.nl.symbols if self.search_box.value in item
            ]
            self.list.options = filtered_options


_help_message_style = """


<style >
  .help-section {
    margin-left: 5px;}

  .help-header {
    background: lightGray;
    border-bottom: 1px solid black;}

  .help-body {
    padding-left: 5px;
    padding-top: 5px;}

  .unavailable {
    background: lightyellow;}
</style >
"""


def _format_help_message(symbol: str, help: Optional[str]) -> str:
    body = (
        f"<pre>{html.escape(help)}</pre>"
        if help is not None
        else "<p class='unavailable'>help unavailable</p>"
    )

    markup = f"""
    {_help_message_style}
    <div class = "help-section" >
      <p class = "help-header" >
        <i class = "fa fa-fw fa-question-circle" aria-hidden = "true" > </i > help for <b> {symbol} </b>
      </p >
      <div class = "help-body" >
        {body}
      </div >
    </div >
    """
    return markup


class QueryWidget(VBox):
    """
    A widget to input queries

    Parameters
    ----------

    neurolang_engine: NeurolangDL
                      Engine to query
    default_query: str
                   Default query text, will be shown in textarea
    reraise: bool
             re-raise exceptions thrown during query execution
    """

    def __init__(
        self,
        neurolang_engine,
        default_query="ans(region_union(r)) :- destrieux(..., r)",
        reraise=False,
    ):
        super().__init__()

        # TODO check if neurolang_engine is None.

        self.neurolang_engine = neurolang_engine
        self.reraise = reraise

        self.query = NlCodeEditor(
            default_query,
            disabled=False,
            layout=Layout(
                display="flex",
                flex_flow="row",
                align_items="stretch",
                width="75%",
                height="100px",
                border="solid 1px silver",
            ),
        )
        self.button = Button(description="Run query")
        self.button.on_click(self._on_query_button_clicked)
        self.error_display = HTML(layout=Layout(visibility="hidden"))
        self.query_section = Tab(
            children=[
                VBox([HBox([self.query, self.button]), self.error_display]),
                SymbolsWidget(self.neurolang_engine),
            ]
        )
        for i, tab_title in enumerate(["query", "symbols"]):
            self.query_section.set_title(i, tab_title)

        self.result_viewer = QResultWidget()

        self.children = [self.query_section, self.result_viewer]

    def run_query(self, query: str):
        with self.neurolang_engine.scope:
            self.neurolang_engine.execute_datalog_program(query)
            res = self.neurolang_engine.solve_all()
            predicate_names = {
                k: self.neurolang_engine.predicate_parameter_names(k) for k in res
            }
            return res, predicate_names

    def _on_query_button_clicked(self, b):
        """Runs the query in the query text area and diplays the results.

        Parameters
        ----------
        b: ipywidgets.Button
            button clicked.
        """

        self._reset_output()

        try:
            qresult, pnames = self.run_query(self.query.text)
        except FailedParse as fp:
            self._set_error_marker(fp)
            self._handle_generic_error(fp)
        except Exception as e:
            self.handle_generic_error(e)
        else:
            self.result_viewer.show_results(qresult, pnames)
            self.result_viewer.layout.visibility = "visible"

    def _reset_output(self):
        self.query.clear_marks()
        self.result_viewer.reset()
        self.result_viewer.layout.visibility = "hidden"
        self.error_display.layout.visibility = "hidden"

    def _set_error_marker(self, pe: FailedParse):
        try:
            line_info = pe.tokenizer.line_info(pe.pos)
        except AttributeError:
            # support tatsu 4.x
            line_info = pe.buf.line_info(pe.pos)

        self.query.marks = [{"line": line_info.line, "text": pe.message}]
        self.query.text_marks = [
            {
                "from": {"line": line_info.line, "ch": line_info.col},
                "to": {"line": line_info.line, "ch": line_info.col + 1},
            }
        ]

    def _handle_generic_error(self, e: Exception):
        self.error_display.layout.visibility = "visible"
        self.error_display.value = _format_exc(e)
        if self.reraise:
            raise e


def _format_exc(e: Exception):
    """
    Format an exception for display
    """
    return f"<pre style='background-color:#faaba5; border: 1px solid red; padding: 0.4em'>{e}</pre>"
