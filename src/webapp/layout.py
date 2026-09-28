"""Layout de la aplicación Dash (front-end)."""

import dash_bootstrap_components as dbc
from dash import dcc, html


class IDs:
    """Identificadores únicos de todos los componentes reactivos."""
    SEARCH = "search-input"
    RANGE = "date-range"
    KIND = "kind-select"
    CATEGORY = "category-select"
    RESET = "reset-btn"
    RECORDS_ONLY = "records-only-check"

    TABLE = "main-table"
    PAGE_SIZE = "page-size"
    RESULT_COUNT = "result-count"

    DETAIL = "detail-card"
    ACTIVE = "table-active"

    EXPORT_CSV = "export-csv"
    EXPORT_JSON = "export-json"
    DOWNLOAD = "download"

    # ---- Verificador de actualizaciones ----
    CHECK_BTN = "check-updates-btn"
    UPDATES_RESULT = "updates-result"
    UPDATES_STATUS = "updates-status"
    DOWNLOAD_NEW = "download-new-btn"
    UPDATES_STORE = "updates-store"
    CLOSE_RESULT = "close-updates-btn"
    UPDATES_RESULT_INNER = "updates-result-inner"
    DATA_VERSION = "data-version"

    # ---- Métricas (para refrescar tras descargar novedades) ----
    M_TOTAL = "metric-total"
    M_POSTS = "metric-posts"
    M_CMS = "metric-cms"
    M_EVENTOS = "metric-eventos"
    M_DOCS = "metric-docs"
    M_IMGS = "metric-imgs"
    M_CATS = "metric-cats"
    M_CHARS = "metric-chars"

    # ---- Métricas interactivas (tarjetas con clic) ----
    CARD_TOTAL = "metric-card-total"
    CARD_POSTS = "metric-card-posts"
    CARD_CMS = "metric-card-cms"
    CARD_EVENTOS = "metric-card-eventos"
    CARD_DOCS = "metric-card-docs"
    CARD_IMGS = "metric-card-imgs"
    CARD_CATS = "metric-card-cats"
    CARD_CHARS = "metric-card-chars"

    # ---- Filtros adicionales en barra de consulta ----
    HAS_DOCS_FILTER = "filter-has-docs"
    HAS_IMGS_FILTER = "filter-has-imgs"

    # ---- Modal explorador de adjuntos ----
    DOCS_MODAL = "docs-modal"
    DOCS_MODAL_CLOSE = "docs-modal-close"
    DOCS_SEARCH = "docs-search-input"
    DOCS_CONTAINER = "docs-container"
    DOCS_PAGE = "docs-page-store"
    DOCS_PREV = "docs-prev-btn"
    DOCS_NEXT = "docs-next-btn"
    DOCS_PAGE_INFO = "docs-page-info"
    DOCS_FILTER_BTN = "docs-filter-main-btn"

    # ---- Modal galería de imágenes ----
    IMGS_MODAL = "imgs-modal"
    IMGS_MODAL_CLOSE = "imgs-modal-close"
    IMGS_SEARCH = "imgs-search-input"
    IMGS_CONTAINER = "imgs-container"
    IMGS_PAGE = "imgs-page-store"
    IMGS_PREV = "imgs-prev-btn"
    IMGS_NEXT = "imgs-next-btn"
    IMGS_PAGE_INFO = "imgs-page-info"
    IMGS_FILTER_BTN = "imgs-filter-main-btn"

    # ---- Modal catálogo de categorías ----
    CATS_MODAL = "cats-modal"
    CATS_MODAL_CLOSE = "cats-modal-close"
    CATS_SEARCH = "cats-search-input"
    CATS_CONTAINER = "cats-container"

    # ---- Asistente de IA ----
    ASSISTANT_INPUT = "assistant-input"
    ASSISTANT_SEND = "assistant-send"
    ASSISTANT_CHAT = "assistant-chat"
    ASSISTANT_STORE = "assistant-store"
    ASSISTANT_QUESTION = "assistant-question"
    ASSISTANT_FAB = "assistant-fab"
    ASSISTANT_OC = "assistant-offcanvas"
    ASSISTANT_OC_CLOSE = "assistant-oc-close"
    ASSISTANT_OC_OPEN = "assistant-oc-open"

    # ---- Overlay de carga pantalla completa ----
    LOADING_OVERLAY = "loading-overlay-modal"

    # ---- Selección de registro (tabla + fuentes del asistente) ----
    SELECTED_URL = "selected-url"

    # ---- Lectura de documento (modal exclusivo) ----
    DOC_MODAL = "doc-modal"
    DOC_MODAL_BODY = "doc-modal-body"
    DOC_MODAL_OPEN = "doc-modal-open"
    DOC_MODAL_TITLE = "doc-modal-title"
    READ_FULL = "read-full-btn"

    # ---- Resumen IA del registro ----
    SUMM_BTN = "summ-ia-btn"
    SUMM_OUT = "summ-ia-out"
    SUMM_MODAL_BTN = "summ-ia-modal-btn"
    SUMM_MODAL_OUT = "summ-ia-modal-out"
    SUMM_STORE = "summ-ia-store"

    # ---- Visualización de imagen extraída (gráfica del PDF) a pantalla completa ----
    FULLIMG_MODAL = "fullimg-modal"
    FULLIMG_TITLE = "fullimg-modal-title"
    FULLIMG_BODY = "fullimg-modal-body"
    FULLIMG_OPEN = "fullimg-open"
    FULLIMG_CLOSE = "fullimg-modal-close"

    # ---- Buscador especializado de cifras y estadísticas ----
    CIFRAS_MODAL = "cifras-modal"
    CIFRAS_MODAL_CLOSE = "cifras-modal-close"
    CIFRAS_OPEN_BTN = "cifras-open-btn"
    CIFRAS_CARD = "cifras-card"
    CIFRAS_INPUT = "cifras-input"
    CIFRAS_SEARCH_BTN = "cifras-search-btn"
    CIFRAS_ORIGIN = "cifras-origin-select"
    CIFRAS_CONTAINER = "cifras-container"
    CIFRAS_COUNT_INFO = "cifras-count-info"
    CIFRAS_PAGE = "cifras-page-store"
    CIFRAS_PREV = "cifras-prev-btn"
    CIFRAS_NEXT = "cifras-next-btn"
    CIFRAS_PAGE_INFO = "cifras-page-info"
    CIFRAS_KEYWORDS = "cifras-keywords-input"
    CIFRAS_CRAWL_BTN = "cifras-crawl-btn"
    CIFRAS_CRAWL_STATUS = "cifras-crawl-status"


def _metric_row(stats: dict):
    # 4 tarjetas interactivas: Registros, Adjuntos, Categorías y Buscador de Cifras
    counter_card = dbc.Col(
        _metric_card_static("Registros", f"{stats['total']:,}", "database", IDs.M_TOTAL),
        xs=12, sm=6, md=3,
    )
    docs_card = dbc.Col(
        _metric_card("Adjuntos", f"{stats['documentos']:,}", "paperclip",
                     IDs.M_DOCS, IDs.CARD_DOCS, "Explorar", "primary"),
        xs=12, sm=6, md=3,
    )
    cats_card = dbc.Col(
        _metric_card("Categorías", f"{stats['categorias']:,}", "tags",
                     IDs.M_CATS, IDs.CARD_CATS, "Catálogo", "primary"),
        xs=12, sm=6, md=3,
    )
    cifras_card = dbc.Col(
        _metric_card("Cifras y Datos", "Explorar", "bar-chart-line-fill",
                     "metric-cifras-val", IDs.CIFRAS_CARD, "Rastrear", "warning"),
        xs=12, sm=6, md=3,
    )
    return dbc.Row([counter_card, docs_card, cats_card, cifras_card], className="g-3 mb-3")


def _metric_card_static(label, value, icon, value_id):
    """Tarjeta de métrica sin interactividad (solo contador)."""
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.I(className=f"bi bi-{icon} me-2 text-primary fs-5"),
                html.Span(label, className="small text-muted fw-semibold"),
            ], className="d-flex align-items-center mb-1"),
            html.Span(value, className="fs-3 fw-bold text-primary", id=value_id),
        ], className="py-2 px-3"),
        className="shadow-sm h-100 border-0",
    )


def _metric_card(label, value, icon, value_id, card_id, badge_text="Ver", badge_color="light"):
    """Tarjeta de métrica interactiva (abre modal al hacer clic)."""
    value_div = html.Span(value, className="fs-3 fw-bold text-primary", id=value_id)
    return html.Div(
        dbc.Card(
            dbc.CardBody([
                html.Div([
                    html.I(className=f"bi bi-{icon} me-2 text-primary fs-5"),
                    html.Span(label, className="small text-muted fw-semibold"),
                    dbc.Badge(badge_text, color=badge_color, className="ms-auto small", pill=True),
                ], className="d-flex align-items-center mb-1"),
                html.Div([
                    value_div,
                    html.I(className="bi bi-chevron-right text-muted small"),
                ], className="d-flex align-items-center justify-content-between mt-1"),
            ], className="py-2 px-3"),
            className="shadow-sm h-100 metric-card-interactive border-0",
        ),
        id=card_id,
        n_clicks=0,
        style={"cursor": "pointer"},
        title=f"Haz clic para explorar {label.lower()}",
    )


def build_layout(categories: list, stats: dict, ai_status: dict = None):
    """Construye la estructura visual de la aplicación."""

    # ---- Indicador de estado de IA en la barra de navegación ----
    if ai_status is None:
        ai_status = {}
    _ai_ok = ai_status.get("ok", False)
    _ai_label = ai_status.get("label", "IA no configurada")
    _ai_detail = ai_status.get("detail", "")
    _ai_model = ai_status.get("model", "")
    _ai_latency = ai_status.get("latency_ms")

    # Texto breve para la línea principal del badge
    _badge_main = "IA operativa" if _ai_ok else "IA no disponible"
    # Subtexto: modelo + latencia si está ok; label completo si hay error
    if _ai_ok:
        _badge_sub_parts = []
        if _ai_model:
            _badge_sub_parts.append(_ai_model)
        if _ai_latency is not None:
            _badge_sub_parts.append(f"{_ai_latency} ms")
        _badge_sub = " · ".join(_badge_sub_parts)
    else:
        # Mostrar solo la parte después del primer "·" si hay, para no repetir
        _badge_sub = _ai_label.split("·", 1)[-1].strip() if "·" in _ai_label else _ai_label

    _tooltip = f"{_ai_label}"
    if _ai_detail:
        _tooltip += f"\n{_ai_detail}"

    ai_badge = html.Div([
        # Punto LED animado
        html.Span(className="ai-status-dot " + ("ai-status-ok" if _ai_ok else "ai-status-err")),
        html.Div([
            html.Span(
                _badge_main,
                className="small fw-semibold d-block lh-1",
            ),
            html.Span(
                _badge_sub,
                className="text-white-50 lh-1 d-none d-lg-inline",
                style={"fontSize": "10px"},
            ),
        ], className="ms-2 d-none d-md-flex flex-column"),
    ],
        id="ai-status-badge",
        title=_tooltip,
        className="d-flex align-items-center ai-status-badge px-2 py-1 rounded-2",
        style={
            "cursor": "help",
            "backgroundColor": "rgba(255,255,255,0.12)" if _ai_ok else "rgba(255,80,80,0.18)",
            "border": "1px solid rgba(255,255,255,0.2)" if _ai_ok else "1px solid rgba(255,120,120,0.4)",
        }
    )


    navbar = dbc.Navbar(
        dbc.Container([
            html.A([
                html.Span("F E N A L C O", className="fw-bold text-white fs-4"),
                html.Span(" · Centro de Datos Públicos",
                          className="text-white-50 ms-2"),
            ], href="/", className="navbar-brand me-auto"),
            ai_badge,
        ], className="d-flex align-items-center"),
        color="primary", dark=True, className="mb-3 shadow-sm",
    )

    filters = dbc.Card([
        dbc.CardHeader(html.H6("Filtros y consulta", className="mb-0 fw-bold")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Buscar por título, contenido o palabra clave",
                              className="small fw-bold"),
                    dbc.Input(id=IDs.SEARCH, type="text",
                              placeholder="Ej.: reforma tributaria, decreto 566, dia sin iva…",
                              debounce=True),
                ], md=4),
                dbc.Col([
                    dbc.Label("Tipo de contenido", className="small fw-bold"),
                    dcc.Dropdown(
                        id=IDs.KIND,
                        options=[
                            {"label": "Blog / Noticia", "value": "blog-post"},
                            {"label": "Página / CMS", "value": "cms"},
                            {"label": "Evento", "value": "event"},
                        ],
                        multi=True, placeholder="Todos los tipos", clearable=True),
                ], md=3),
                dbc.Col([
                    dbc.Label("Categoría", className="small fw-bold"),
                    dcc.Dropdown(
                        id=IDs.CATEGORY,
                        options=[{"label": c, "value": c} for c in categories],
                        multi=True, placeholder="Todas las categorías", clearable=True),
                ], md=3),
                dbc.Col([
                    dbc.Label("Rango de fechas", className="small fw-bold"),
                    dcc.DatePickerRange(id=IDs.RANGE,
                                        start_date_placeholder_text="Desde",
                                        end_date_placeholder_text="Hasta",
                                        display_format="YYYY-MM-DD",
                                        className="w-100"),
                ], md=2),
            ], className="align-items-end"),
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(
                        id=IDs.RECORDS_ONLY,
                        options=[{"label": "Solo registros con texto",
                                  "value": "yes"}],
                        value=[], switch=True, className="mt-2 d-inline-block me-3"),
                    dbc.Checklist(
                        id=IDs.HAS_DOCS_FILTER,
                        options=[{"label": "Solo con adjuntos",
                                  "value": "yes"}],
                        value=[], switch=True, className="mt-2 d-inline-block me-3"),
                    dbc.Checklist(
                        id=IDs.HAS_IMGS_FILTER,
                        options=[{"label": "Solo con imágenes",
                                  "value": "yes"}],
                        value=[], switch=True, className="mt-2 d-inline-block"),
                ], md=6),
                dbc.Col([
                    dbc.ButtonGroup([
                        dbc.Button([html.I(className="bi bi-bar-chart-line-fill me-1 text-warning"),
                                    "Buscador de Cifras"], id=IDs.CIFRAS_OPEN_BTN,
                                   color="primary", size="sm", n_clicks=0, className="fw-semibold"),
                        dbc.Button("Limpiar filtros", id=IDs.RESET,
                                   color="secondary", outline=True,
                                   size="sm", n_clicks=0),
                        dbc.Button([html.I(className="bi bi-filetype-csv me-1"),
                                    "Exportar CSV filtrado"], id=IDs.EXPORT_CSV,
                                   color="info", size="sm", n_clicks=0),
                        dbc.Button([html.I(className="bi bi-filetype-json me-1"),
                                    "Exportar JSON de la fila"], id=IDs.EXPORT_JSON,
                                   color="dark", size="sm", n_clicks=0),
                    ], className="mt-2"),
                ], md=6, className="text-md-end"),
            ]),
        ]),
    ], className="shadow-sm mb-3")

    # ---- Verificador de actualizaciones ----
    updates_card = dbc.Card([
        dbc.CardHeader(html.H6("Verificador de actualizaciones",
                               className="mb-0 fw-bold")),
        dbc.CardBody([
            html.P("Compara el sitemap actual del sitio con los datos "
                   "almacenados y detecta contenido nuevo, modificado o "
                   "retirado. Pulsa «Comprobar ahora» para revisar.",
                   className="text-muted small mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Button([html.I(className="bi bi-arrow-repeat me-1"),
                                "Comprobar ahora"],
                               id=IDs.CHECK_BTN, color="primary",
                               n_clicks=0, className="me-2"),
                    dbc.Button([html.I(className="bi bi-download me-1"),
                                "Descargar novedades"],
                               id=IDs.DOWNLOAD_NEW, color="success",
                               n_clicks=0, disabled=True),
                ], md=6),
                dbc.Col([
                    html.Div([
                        html.Span("Estado: ", className="fw-bold text-secondary"),
                        html.Span("En espera. Pulsa «Comprobar ahora».",
                                  id=IDs.UPDATES_STATUS, className="small"),
                    ], className="mb-1"),
                    html.Div([
                        html.Span("Datos: ", className="fw-bold text-secondary"),
                        html.Span(f"{stats['total']:,} registros",
                                  id=IDs.DATA_VERSION, className="small"),
                    ], className="mb-1"),
                ], md=6),
            ], className="align-items-start"),
            dbc.Collapse(
                id=IDs.UPDATES_RESULT,
                is_open=False,
                children=html.Div(
                    id=IDs.UPDATES_RESULT_INNER,
                    className="mt-2",
                    children=_alert(
                        "Pulsa «Comprobar ahora» para ver las novedades.",
                        "info"),
                ),
            ),
            dcc.Store(id=IDs.UPDATES_STORE),
            # Botón oculto necesario para el callback de contraer resultado;
            # el botón real se crea dinámicamente en build_result_panel.
            html.Button(id=IDs.CLOSE_RESULT, n_clicks=0,
                        style={"display": "none"}),
        ]),
    ], className="shadow-sm mb-3")

    table_header = dbc.CardHeader(
        dbc.Row([
            dbc.Col(html.H6(id=IDs.RESULT_COUNT, className="mb-0 fw-bold"),
                    className="align-self-center"),
            dbc.Col([
                dbc.Label("Por página", className="small me-1 fw-bold"),
                dcc.Dropdown(
                    id=IDs.PAGE_SIZE,
                    options=[{"label": str(n), "value": n}
                             for n in (10, 25, 50, 100, 250)],
                    value=25, clearable=False, style={"width": "88px"}),
            ], className="col-auto"),
        ]),
    )

    table = dbc.Card([
        table_header,
        dbc.CardBody([
            dcc.Loading(id="loading-table", type="circle",
                        children=_build_table()),
        ]),
    ], className="shadow-sm")

    detail_side = dbc.Card([
        dbc.CardHeader(html.H6("Detalle del registro",
                               className="mb-0 fw-bold")),
        dbc.CardBody(html.Div(
            id=IDs.DETAIL,
            children=dbc.Alert(
                "Haz clic en una fila para ver su detalle completo.",
                color="info", className="shadow-sm"))),
    ], className="shadow-sm position-sticky", style={"top": "12px"})

    # ---- Asistente de IA (chat) ----
    suggestions = [
        "¿Qué opina FENALCO del salario mínimo?",
        "Informes de vehículos eléctricos",
        "¿Qué dice la reforma laboral?",
        "Impacto del impuesto saludable",
        "Día nacional del tendero",
        "Últimas bitácoras económicas",
    ]
    sugg_chips = [
        html.Button(s, id={"type": "assistant-sugg", "index": s.lower()},
                    n_clicks=0, className="me-1 mb-1 btn btn-sm",
                    style={"border-radius": "1rem",
                           "border": "1px solid var(--bs-primary)",
                           "background": "transparent",
                           "color": "var(--bs-primary)"})
        for s in suggestions
    ]

    # ---- Asistente de IA (widget flotante) ----
    assistant_oc = dbc.Offcanvas(
        [
            dbc.Button([html.I(className="bi bi-x-lg")],
                       id=IDs.ASSISTANT_OC_CLOSE, color="light", size="sm",
                       className="float-end", n_clicks=0, title="Cerrar"),
            html.H6("Asistente FENALCO", className="mb-2"),
            html.P("Pregúntale sobre los datos. Busca en la base y responde "
                   "con las fuentes. Pulsa una fuente para abrir el detalle.",
                   className="text-muted small mb-2"),
            html.Div(sugg_chips, className="mb-2"),
            dcc.Loading(
                id="loading-assistant-chat",
                type="default",
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                custom_spinner=html.Div([
                    html.Div(className="spinner-border spinner-border-sm text-primary me-2",
                             role="status"),
                    html.Span("Cargando contexto de documentos…",
                              className="small text-primary fw-semibold"),
                ], className="d-flex align-items-center justify-content-center py-3"),
                children=html.Div(id=IDs.ASSISTANT_CHAT, className="assistant-chat mb-3"),
            ),
            dbc.InputGroup([
                dbc.Input(id=IDs.ASSISTANT_INPUT, type="text",
                          placeholder="Escribe tu pregunta… (Intro para enviar)",
                          n_submit=0),
                dcc.Loading(
                    id="loading-assistant-send",
                    type="circle",
                    children=dbc.Button([html.I(className="bi bi-send-fill")],
                                        id=IDs.ASSISTANT_SEND, color="primary", n_clicks=0),
                    style={"display": "flex", "alignItems": "center"},
                ),
            ]),
            dcc.Store(id=IDs.ASSISTANT_STORE, data=[]),
            dcc.Store(id=IDs.ASSISTANT_QUESTION, data=None),
            html.P(id="assistant-ai-status",
                   className="small text-muted mt-2 mb-0"),
        ],
        id=IDs.ASSISTANT_OC,
        placement="end",
        is_open=False,
        backdrop=False,
        scrollable=True,
        close_button=False,
        style={"zIndex": 1045, "boxShadow": "-4px 0 24px rgba(0,0,0,0.15)"},
    )

    fab = html.Button(
        [html.I(className="bi bi-stars fs-5 me-2"),
         html.Span("Asistente", className="d-none d-sm-inline")],
        id=IDs.ASSISTANT_FAB,
        className="assistant-fab shadow",
        n_clicks=0,
        style={
            "position": "fixed", "bottom": "22px", "right": "22px",
            "zIndex": 1100, "borderRadius": "2rem", "border": "none",
            "padding": "0.7rem 1.1rem", "fontWeight": "600",
            "background": "linear-gradient(90deg, #084a86, #0b5cab)",
            "color": "#fff",
        },
    )

    footer = html.Footer([
        html.P("Datos públicos extraídos de fenalco.com.co. Filtra, ordena, "
               "selecciona filas y exporta el conjunto completo de registros.",
               className="text-center text-muted small mb-0"),
    ], className="mt-4 border-top pt-3")

    # ---- Modal de lectura de documento (apartado exclusivo) ----
    doc_modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(
                html.Span(id=IDs.DOC_MODAL_TITLE,
                          children="Documento"))),
            dbc.ModalBody(
                html.Div(id=IDs.DOC_MODAL_BODY,
                         style={"maxHeight": "72vh", "overflowY": "auto"})),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id=IDs.DOC_MODAL_OPEN + "-close",
                           className="ms-auto", color="secondary", n_clicks=0)),
        ],
        id=IDs.DOC_MODAL,
        is_open=False,         # cerrado por defecto, controlado por callback
        size="xl",             # muy ancho para leer cómodo
        scrollable=True,
        backdrop="static",
        centered=True,
        style={"zIndex": 2100},
    )

    # ---- Modal de visualización de imagen extraída (gráfica) a pantalla completa ----
    fullimg_modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(
                html.Span(id=IDs.FULLIMG_TITLE, children="Imagen extraída"))),
            dbc.ModalBody(
                html.Div(id=IDs.FULLIMG_BODY, style={"textAlign": "center"}),
                style={"overflow": "auto"}),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id=IDs.FULLIMG_CLOSE,
                           className="ms-auto", color="secondary", n_clicks=0)),
        ],
        id=IDs.FULLIMG_MODAL,
        is_open=False,         # controlado por callback
        size="xl",             # muy ancho para ver la gráfica completa
        scrollable=True,
        centered=True,
        style={"zIndex": 2200},
    )

    # ---- Modal explorador de adjuntos ----
    docs_modal = dbc.Modal(
        [
            dbc.ModalHeader([
                html.Div([
                    html.I(className="bi bi-paperclip me-2 text-primary fs-4"),
                    html.Span(f"Explorador de Adjuntos ({stats['documentos']:,} archivos)", className="fw-bold fs-5"),
                ], className="d-flex align-items-center"),
                dbc.Button(html.I(className="bi bi-x-lg"), id=IDs.DOCS_MODAL_CLOSE,
                           color="light", size="sm", className="ms-auto", n_clicks=0),
            ], close_button=False),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className="bi bi-search")),
                            dbc.Input(
                                id=IDs.DOCS_SEARCH,
                                type="text",
                                placeholder="Buscar en adjuntos por nombre de archivo o título de artículo…",
                                debounce=True,
                            ),
                        ]),
                    ], md=8),
                    dbc.Col([
                        dbc.Button(
                            [html.I(className="bi bi-funnel me-1"), "Filtrar tabla por registros con adjuntos"],
                            id=IDs.DOCS_FILTER_BTN,
                            color="outline-primary",
                            size="sm",
                            className="w-100",
                            n_clicks=0,
                        ),
                    ], md=4, className="text-end"),
                ], className="g-2 mb-3 align-items-center"),
                dcc.Loading(
                    id="loading-docs-list",
                    type="circle",
                    children=html.Div(id=IDs.DOCS_CONTAINER, style={"minHeight": "320px", "maxHeight": "60vh", "overflowY": "auto"}),
                ),
                dcc.Store(id=IDs.DOCS_PAGE, data=0),
                dbc.Row([
                    dbc.Col(html.Span(id=IDs.DOCS_PAGE_INFO, className="small text-muted align-self-center"), xs=12, sm=6),
                    dbc.Col([
                        dbc.ButtonGroup([
                            dbc.Button("« Anterior", id=IDs.DOCS_PREV, color="secondary", outline=True, size="sm", n_clicks=0),
                            dbc.Button("Siguiente »", id=IDs.DOCS_NEXT, color="secondary", outline=True, size="sm", n_clicks=0),
                        ]),
                    ], xs=12, sm=6, className="text-end mt-2 mt-sm-0"),
                ], className="mt-3 pt-2 border-top align-items-center"),
            ]),
        ],
        id=IDs.DOCS_MODAL,
        is_open=False,
        size="xl",
        scrollable=True,
        centered=True,
        style={"zIndex": 2110},
    )

    # ---- Modal galería visual de imágenes ----
    imgs_modal = dbc.Modal(
        [
            dbc.ModalHeader([
                html.Div([
                    html.I(className="bi bi-image me-2 text-primary fs-4"),
                    html.Span(f"Galería de Imágenes ({stats['imagenes']:,} imágenes)", className="fw-bold fs-5"),
                ], className="d-flex align-items-center"),
                dbc.Button(html.I(className="bi bi-x-lg"), id=IDs.IMGS_MODAL_CLOSE,
                           color="light", size="sm", className="ms-auto", n_clicks=0),
            ], close_button=False),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className="bi bi-search")),
                            dbc.Input(
                                id=IDs.IMGS_SEARCH,
                                type="text",
                                placeholder="Buscar en imágenes por título de publicación o categoría…",
                                debounce=True,
                            ),
                        ]),
                    ], md=8),
                    dbc.Col([
                        dbc.Button(
                            [html.I(className="bi bi-funnel me-1"), "Filtrar tabla por registros con imágenes"],
                            id=IDs.IMGS_FILTER_BTN,
                            color="outline-primary",
                            size="sm",
                            className="w-100",
                            n_clicks=0,
                        ),
                    ], md=4, className="text-end"),
                ], className="g-2 mb-3 align-items-center"),
                dcc.Loading(
                    id="loading-imgs-list",
                    type="circle",
                    children=html.Div(id=IDs.IMGS_CONTAINER, style={"minHeight": "320px", "maxHeight": "60vh", "overflowY": "auto"}),
                ),
                dcc.Store(id=IDs.IMGS_PAGE, data=0),
                dbc.Row([
                    dbc.Col(html.Span(id=IDs.IMGS_PAGE_INFO, className="small text-muted align-self-center"), xs=12, sm=6),
                    dbc.Col([
                        dbc.ButtonGroup([
                            dbc.Button("« Anterior", id=IDs.IMGS_PREV, color="secondary", outline=True, size="sm", n_clicks=0),
                            dbc.Button("Siguiente »", id=IDs.IMGS_NEXT, color="secondary", outline=True, size="sm", n_clicks=0),
                        ]),
                    ], xs=12, sm=6, className="text-end mt-2 mt-sm-0"),
                ], className="mt-3 pt-2 border-top align-items-center"),
            ]),
        ],
        id=IDs.IMGS_MODAL,
        is_open=False,
        size="xl",
        scrollable=True,
        centered=True,
        style={"zIndex": 2110},
    )

    # ---- Modal catálogo de categorías ----
    cats_modal = dbc.Modal(
        [
            dbc.ModalHeader([
                html.Div([
                    html.I(className="bi bi-tags me-2 text-primary fs-4"),
                    html.Span(f"Catálogo de Categorías ({stats['categorias']:,} categorías)", className="fw-bold fs-5"),
                ], className="d-flex align-items-center"),
                dbc.Button(html.I(className="bi bi-x-lg"), id=IDs.CATS_MODAL_CLOSE,
                           color="light", size="sm", className="ms-auto", n_clicks=0),
            ], close_button=False),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className="bi bi-search")),
                            dbc.Input(
                                id=IDs.CATS_SEARCH,
                                type="text",
                                placeholder="Buscar categoría…",
                                debounce=True,
                            ),
                        ]),
                    ], md=12),
                ], className="mb-3"),
                html.P("Haz clic en cualquier categoría para seleccionarla en los filtros y ver sus publicaciones:",
                       className="text-muted small mb-3"),
                dcc.Loading(
                    id="loading-cats-list",
                    type="circle",
                    children=html.Div(id=IDs.CATS_CONTAINER, style={"minHeight": "280px", "maxHeight": "60vh", "overflowY": "auto"}),
                ),
            ]),
        ],
        id=IDs.CATS_MODAL,
        is_open=False,
        size="lg",
        scrollable=True,
        centered=True,
        style={"zIndex": 2110},
    )

    # ---- Modal Buscador de Cifras y Estadísticas ----
    cifras_modal = dbc.Modal(
        [
            dbc.ModalHeader([
                html.Div([
                    html.I(className="bi bi-bar-chart-line-fill me-2 text-warning fs-4"),
                    html.Div([
                        html.Span("Buscador de Cifras, Porcentajes y Estadísticas", className="fw-bold fs-5 d-block"),
                        html.Span("Búsqueda determinística exacta en publicaciones, documentos PDF y gráficas con OCR", className="small text-muted"),
                    ]),
                ], className="d-flex align-items-center"),
                dbc.Button(html.I(className="bi bi-x-lg"), id=IDs.CIFRAS_MODAL_CLOSE,
                           color="light", size="sm", className="ms-auto", n_clicks=0),
            ], close_button=False),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Cifra o porcentaje a buscar", className="small fw-semibold text-secondary mb-1"),
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className="bi bi-percent fs-5 text-primary")),
                            dbc.Input(
                                id=IDs.CIFRAS_INPUT,
                                type="text",
                                placeholder="Ej: 26%, 1.4%, 550, 48%…",
                                debounce=True,
                            ),
                        ]),
                    ], xs=12, md=5),
                    dbc.Col([
                        dbc.Label("Palabras clave de filtro (opcional)", className="small fw-semibold text-secondary mb-1"),
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className="bi bi-funnel text-primary")),
                            dbc.Input(
                                id=IDs.CIFRAS_KEYWORDS,
                                type="text",
                                placeholder="Ej: tendero, tiendas, impuestos, supervivencia…",
                                debounce=True,
                            ),
                        ]),
                    ], xs=12, md=5),
                    dbc.Col([
                        dbc.Label("Acción", className="small fw-semibold text-transparent mb-1 d-none d-md-block"),
                        dbc.Button([
                            html.I(className="bi bi-search me-1"),
                            "Buscar en Todo"
                        ], id=IDs.CIFRAS_SEARCH_BTN, color="primary", className="w-100 fw-semibold", n_clicks=0),
                    ], xs=12, md=2),
                ], className="g-2 mb-2 align-items-end"),
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.Span("Sugerencias: ", className="small text-muted me-2 fw-semibold"),
                            dbc.Button("26%", id={"type": "cifra-chip-btn", "index": "26%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("1.4%", id={"type": "cifra-chip-btn", "index": "1.4%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("40%", id={"type": "cifra-chip-btn", "index": "40%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("51%", id={"type": "cifra-chip-btn", "index": "51%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("550%", id={"type": "cifra-chip-btn", "index": "550%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("48%", id={"type": "cifra-chip-btn", "index": "48%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                            dbc.Button("13.8%", id={"type": "cifra-chip-btn", "index": "13.8%"}, size="sm", color="light", className="me-1 border rounded-pill py-0 px-2 small fw-semibold text-primary", n_clicks=0),
                        ], className="d-flex align-items-center flex-wrap"),
                    ], md=8),
                    dbc.Col([
                        dbc.RadioItems(
                            id=IDs.CIFRAS_ORIGIN,
                            options=[
                                {"label": "Todos", "value": "all"},
                                {"label": "Artículos", "value": "articulos"},
                                {"label": "PDFs", "value": "documentos"},
                                {"label": "Gráficas OCR", "value": "graficas"},
                            ],
                            value="all",
                            inline=True,
                            className="small text-md-end mt-1 mt-md-0",
                        ),
                    ], md=4, className="text-md-end"),
                ], className="g-2 mb-3 align-items-center"),
                html.Div(id=IDs.CIFRAS_COUNT_INFO, className="mb-2"),
                dcc.Loading(
                    id="loading-cifras-list",
                    type="circle",
                    children=html.Div(id=IDs.CIFRAS_CONTAINER, style={"minHeight": "320px", "maxHeight": "58vh", "overflowY": "auto"}),
                ),
                dcc.Store(id=IDs.CIFRAS_PAGE, data=0),
                dbc.Row([
                    dbc.Col(html.Span(id=IDs.CIFRAS_PAGE_INFO, className="small text-muted align-self-center"), xs=12, sm=6),
                    dbc.Col([
                        dbc.ButtonGroup([
                            dbc.Button("« Anterior", id=IDs.CIFRAS_PREV, color="secondary", outline=True, size="sm", n_clicks=0),
                            dbc.Button("Siguiente »", id=IDs.CIFRAS_NEXT, color="secondary", outline=True, size="sm", n_clicks=0),
                        ]),
                    ], xs=12, sm=6, className="text-end mt-2 mt-sm-0"),
                ], className="mt-3 pt-2 border-top align-items-center"),
            ]),
        ],
        id=IDs.CIFRAS_MODAL,
        is_open=False,
        size="xl",
        scrollable=True,
        centered=True,
        style={"zIndex": 2120},
    )

    # ---- Overlay de carga pantalla completa ----
    loading_overlay = html.Div(
        [
            html.Div([
                html.Div(
                    className="spinner-border text-light mb-3",
                    role="status",
                    style={"width": "3.5rem", "height": "3.5rem",
                           "borderWidth": "0.35rem"},
                ),
                html.H5("Consultando la base de datos de FENALCO…",
                        className="text-white fw-semibold mb-1"),
                html.P("El asistente está buscando, leyendo documentos y "
                       "preparando tu respuesta. Un momento.",
                        className="text-white-50 small mb-0"),
            ], className="text-center"),
        ],
        id=IDs.LOADING_OVERLAY,
        style={
            "display": "none",          # oculto por defecto (controla un callback en el navegador)
            "position": "fixed",
            "top": "0", "left": "0",
            "width": "100vw", "height": "100vh",
            "background": "rgba(8, 30, 63, 0.85)",
            "backdropFilter": "blur(8px)",
            "WebkitBackdropFilter": "blur(8px)",
            "zIndex": "9999",
            "alignItems": "center",
            "justifyContent": "center",
        },
    )
    # Store que activa/desactiva el overlay (True = visible)
    loading_trigger = dcc.Store(id="loading-overlay-trigger", data=False)

    return html.Div([
        navbar,
        dbc.Container([
            _metric_row(stats),
            filters,
            updates_card,
            dbc.Row([
                dbc.Col(table, md=12, lg=8),
                dbc.Col(detail_side, md=12, lg=4),
            ]),
            footer,
        ], fluid=True),
        fab,
        assistant_oc,
        doc_modal,
        fullimg_modal,
        docs_modal,
        imgs_modal,
        cats_modal,
        cifras_modal,
        loading_overlay,
        loading_trigger,
        dcc.Download(id=IDs.DOWNLOAD),
        dcc.Store(id=IDs.ASSISTANT_OC_OPEN, data=False),
        dcc.Store(id=IDs.SELECTED_URL, data=None),
        dcc.Store(id=IDs.DOC_MODAL_OPEN, data=None),   # url a mostrar
        dcc.Store(id=IDs.FULLIMG_OPEN, data=None),     # {src, caption} a mostrar
        dcc.Store(id=IDs.SUMM_STORE, data=None),        # {url, title} para resumen IA
    ], style={"backgroundColor": "var(--bs-body-bg)", "minHeight": "100vh"})


def _alert(message, color):
    import dash_bootstrap_components as _dbc
    return _dbc.Alert(message, color=color, className="mb-0")


def _build_table():
    from dash import dash_table
    return dash_table.DataTable(
        id=IDs.TABLE,
        columns=[
            {"name": "Título", "id": "title"},
            {"name": "Tipo", "id": "tipo"},
            {"name": "Categoría", "id": "category"},
            {"name": "Publicado", "id": "publish_date"},
            {"name": "Caract.", "id": "text_chars", "type": "numeric"},
            {"name": "Docs", "id": "n_documents", "type": "numeric"},
            {"name": "Img", "id": "n_images", "type": "numeric"},
            {"name": "", "id": "url"},
        ],
        sort_action="custom",
        sort_mode="multi",
        page_action="custom",
        page_current=0,
        page_size=25,
        row_selectable=False,
        style_table={"overflowX": "auto"},
        style_cell={
            "textAlign": "left",
            "fontSize": "14px",
            "padding": "6px 10px",
        },
        style_cell_conditional=[
            {"if": {"column_id": "text_chars"}, "textAlign": "right"},
            {"if": {"column_id": "n_documents"}, "textAlign": "right"},
            {"if": {"column_id": "n_images"}, "textAlign": "right"},
            # Ocultar la columna url (solo se usa internamente para la selección)
            {"if": {"column_id": "url"}, "display": "none"},
        ],
        style_header_conditional=[
            {"if": {"column_id": "url"}, "display": "none"},
        ],
        style_header={
            "fontWeight": "bold",
            "backgroundColor": "rgba(11,92,171,.07)",
            "color": "#0b3a66",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"},
             "backgroundColor": "rgba(0,0,0,.02)"},
        ],
        tooltip_delay=120,
        tooltip_duration=None,
    )