"""Callbacks de la aplicación Dash (lógica reactiva)."""

import math

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

from .data import FenalcoData
from .detail import build_detail
from .layout import IDs
from .updates import UpdateVerifier, build_result_panel
from .assistant import Assistant

# Nombres internos de DataFrame que se muestran en la tabla
TABLE_COLS = ["title", "tipo", "category", "publish_date",
              "text_chars", "n_documents", "n_images", "url"]


def _page_data(data: FenalcoData, search, kinds, categories, start, end,
               only_text, has_docs, has_imgs, sort_by, page_current, page_size):
    """Aplica filtros + orden + paginación y devuelve lo que la tabla necesita."""
    df = data.query(search=search or "", kinds=kinds, categories=categories,
                    date_from=start, date_to=end,
                    only_docs=bool(has_docs), only_images=bool(has_imgs))

    if only_text:
        df = df[df["text_chars"] > 0]

    df = data.order(df, sort_by)

    total = int(len(df))
    page_count = max(1, math.ceil(total / page_size))
    page = max(0, min(page_current, page_count - 1))

    start_i = page * page_size
    page_df = df.iloc[start_i: start_i + page_size].copy()

    # JSON-safe: convertir numéricos a int estándar
    for col in ("text_chars", "n_documents", "n_images"):
        page_df[col] = page_df[col].fillna(0).astype(int)

    page_df = page_df[[c for c in TABLE_COLS if c in page_df.columns]]
    rows = page_df.to_dict(orient="records")

    return rows, page_count, page, total


def register_callbacks(app, data: FenalcoData):
    # Instancia compartida del asistente IA (reutilizada por todos los callbacks)
    _assistant = Assistant(data)

    # ------------------------------------------------------------------
    # 1) Datos de la tabla (filtros + orden + paginación)
    @app.callback(
        Output(IDs.TABLE, "data"),
        Output(IDs.TABLE, "page_count"),
        Output(IDs.RESULT_COUNT, "children"),
        Output(IDs.TABLE, "tooltip_data"),
        Input(IDs.TABLE, "sort_by"),
        Input(IDs.TABLE, "page_current"),
        Input(IDs.PAGE_SIZE, "value"),
        Input(IDs.SEARCH, "value"),
        Input(IDs.KIND, "value"),
        Input(IDs.CATEGORY, "value"),
        Input(IDs.RANGE, "start_date"),
        Input(IDs.RANGE, "end_date"),
        Input(IDs.RECORDS_ONLY, "value"),
        Input(IDs.HAS_DOCS_FILTER, "value"),
        Input(IDs.HAS_IMGS_FILTER, "value"),
    )
    def update_table(sort_by, page_current, page_size, search, kinds,
                     categories, start, end, only_text, has_docs, has_imgs):
        page_size = page_size or 25
        rows, page_count, _page, total = _page_data(
            data, search, kinds, categories, start, end,
            only_text, has_docs, has_imgs, sort_by or [], page_current or 0, page_size)

        tooltip_data = [
            {"title": r.get("title", ""),
             "category": str(r.get("category", "")),
             "publish_date": str(r.get("publish_date", ""))}
            for r in rows
        ]
        count_text = (f"{total:,} resultado{'s' if total != 1 else ''} "
                      f"· pág. {_page + 1}/{page_count}")
        return rows, page_count, count_text, tooltip_data
# ------------------------------------------------------------------
    # 2) Volver a la primera página cuando cambian los filtros
    @app.callback(
        Output(IDs.TABLE, "page_current"),
        Input(IDs.SEARCH, "value"),
        Input(IDs.KIND, "value"),
        Input(IDs.CATEGORY, "value"),
        Input(IDs.RANGE, "start_date"),
        Input(IDs.RANGE, "end_date"),
        Input(IDs.RECORDS_ONLY, "value"),
        Input(IDs.HAS_DOCS_FILTER, "value"),
        Input(IDs.HAS_IMGS_FILTER, "value"),
        prevent_initial_call=True,
    )
    def reset_page(*_):
        return 0

    # ------------------------------------------------------------------
    # 3) Tamaño de página
    @app.callback(
        Output(IDs.TABLE, "page_size"),
        Input(IDs.PAGE_SIZE, "value"),
        prevent_initial_call=True,
    )
    def set_page_size(v):
        return v or 25

    # ------------------------------------------------------------------
    # 4) Detalle del registro seleccionado (tabla o fuente del asistente)
    @app.callback(
        Output(IDs.DETAIL, "children"),
        Input(IDs.TABLE, "active_cell"),
        Input(IDs.SELECTED_URL, "data"),
        State(IDs.TABLE, "data"),
        State(IDs.SUMM_STORE, "data"),
    )
    def show_detail(active_cell, selected_url, page_data, summ_store):
        placeholder = _alert("Selecciona una fila o una fuente del asistente "
                             "para ver su detalle.", "info")
        ctx = dash.callback_context

        chosen_url = None
        if ctx.triggered and ctx.triggered[0]["prop_id"] == IDs.SELECTED_URL + ".data":
            chosen_url = selected_url
        elif active_cell and page_data:
            row = page_data[active_cell["row"]]
            chosen_url = row.get("url", "")

        if not chosen_url:
            return placeholder
        record = data.record(chosen_url)
        if not record:
            return placeholder

        existing_summ = (summ_store or {}).get(chosen_url) if (chosen_url and isinstance(summ_store, dict)) else None

        # Detalle + botón para abrir en lectura completa (modal)
        btn = dbc.Button(
            [html.I(className="bi bi-arrows-fullscreen me-1"),
             "Ver en lectura completa"],
            id=IDs.READ_FULL, color="outline-primary", size="sm",
            className="mt-2", n_clicks=0)
        return html.Div([build_detail(record, is_modal=False, existing_summary=existing_summ), btn])

    # ------------------------------------------------------------------
    # 4b) (se consolida en el callback 15 que controla DOC_MODAL_OPEN)
# ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 5) Manejar clics en métricas y botones de filtros
    @app.callback(
        Output(IDs.SEARCH, "value"),
        Output(IDs.KIND, "value"),
        Output(IDs.CATEGORY, "value"),
        Output(IDs.RANGE, "start_date"),
        Output(IDs.RANGE, "end_date"),
        Output(IDs.RECORDS_ONLY, "value"),
        Output(IDs.HAS_DOCS_FILTER, "value"),
        Output(IDs.HAS_IMGS_FILTER, "value"),
        Input(IDs.RESET, "n_clicks"),
        Input(IDs.DOCS_FILTER_BTN, "n_clicks"),
        Input(IDs.IMGS_FILTER_BTN, "n_clicks"),
        Input({"type": "cat-select-btn", "index": dash.ALL}, "n_clicks"),
        State(IDs.SEARCH, "value"),
        State(IDs.KIND, "value"),
        State(IDs.CATEGORY, "value"),
        State(IDs.RANGE, "start_date"),
        State(IDs.RANGE, "end_date"),
        State(IDs.RECORDS_ONLY, "value"),
        State(IDs.HAS_DOCS_FILTER, "value"),
        State(IDs.HAS_IMGS_FILTER, "value"),
        prevent_initial_call=True,
    )
    def handle_filters_and_metric_clicks(
        reset_n, docs_filter_n, imgs_filter_n, cat_clicks,
        cur_search, cur_kind, cur_cat, cur_start, cur_end,
        cur_text_only, cur_has_docs, cur_has_imgs
    ):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        trig = ctx.triggered_id

        # Limpiar filtros
        if trig == IDs.RESET:
            return "", None, None, None, None, [], [], []

        # Filtrar desde el modal de adjuntos
        if trig == IDs.DOCS_FILTER_BTN:
            return cur_search, cur_kind, cur_cat, cur_start, cur_end, cur_text_only, ["yes"], cur_has_imgs

        # Filtrar desde el modal de imágenes
        if trig == IDs.IMGS_FILTER_BTN:
            return cur_search, cur_kind, cur_cat, cur_start, cur_end, cur_text_only, cur_has_docs, ["yes"]

        # Filtrar desde el catálogo de categorías
        if isinstance(trig, dict) and trig.get("type") == "cat-select-btn":
            cat_name = trig.get("index")
            if cat_name:
                return cur_search, cur_kind, [cat_name], cur_start, cur_end, cur_text_only, cur_has_docs, cur_has_imgs

        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 6) Exportar CSV del conjunto filtrado
    @app.callback(
        Output(IDs.DOWNLOAD, "data"),
        Input(IDs.EXPORT_CSV, "n_clicks"),
        State(IDs.SEARCH, "value"),
        State(IDs.KIND, "value"),
        State(IDs.CATEGORY, "value"),
        State(IDs.RANGE, "start_date"),
        State(IDs.RANGE, "end_date"),
        State(IDs.RECORDS_ONLY, "value"),
        State(IDs.HAS_DOCS_FILTER, "value"),
        State(IDs.HAS_IMGS_FILTER, "value"),
        prevent_initial_call=True,
    )
    def export_csv(n, search, kinds, categories, start, end, only_text, has_docs, has_imgs):
        if not n:
            return None
        df = data.query(search=search or "", kinds=kinds,
                        categories=categories, date_from=start, date_to=end,
                        only_docs=bool(has_docs), only_images=bool(has_imgs))
        if only_text:
            df = df[df["text_chars"] > 0]
        cols = ["title", "tipo", "category", "publish_date", "lastmod",
                "url", "text_chars", "num_blocks", "n_documents", "n_images"]
        out = df[[c for c in cols if c in df.columns]].copy()
        return dcc.send_data_frame(out.to_csv, "fenalco_filtro.csv", index=False)

    # ------------------------------------------------------------------
    # 7) Exportar JSON del registro seleccionado
    @app.callback(
        Output(IDs.DOWNLOAD, "data", allow_duplicate=True),
        Input(IDs.EXPORT_JSON, "n_clicks"),
        State(IDs.TABLE, "active_cell"),
        State(IDs.TABLE, "data"),
        prevent_initial_call=True,
    )
    def export_json(n, active_cell, page_data):
        if not n:
            return None
        if not active_cell or not page_data:
            return dict(content="{}", filename="registro.json")
        url = page_data[active_cell["row"]].get("url", "")
        payload = data.row_to_jsonl(url)
        return dict(content=payload,
                    filename=f"registro_{url.split('/')[-1]}.json")

    # ------------------------------------------------------------------
    # 8) Verificador de actualizaciones: ejecutar comprobación (manual)
    @app.callback(
        Output(IDs.UPDATES_STORE, "data"),
        Output(IDs.UPDATES_STATUS, "children"),
        Input(IDs.CHECK_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def run_update_check(n_click):
        verifier = UpdateVerifier(data)
        if verifier.is_busy:
            return None, "Comprobación en curso…"
        result = verifier.check(force_sitemap=True)
        tm = verifier.last_check_time
        status = (f"Comprobación {tm} · "
                  f"{len(result['new'])} nuevas, {len(result['modified'])} "
                  f"modificadas, {len(result['deleted'])} retiradas.")
        return _encode_update(result), status

    # ------------------------------------------------------------------
    # 9) Render del panel del verificador a partir del store
    @app.callback(
        Output(IDs.UPDATES_RESULT_INNER, "children"),
        Output(IDs.DOWNLOAD_NEW, "disabled"),
        Input(IDs.UPDATES_STORE, "data"),
    )
    def render_update_result(data_encoded):
        if not data_encoded:
            return _alert("Pulsa «Comprobar ahora» para ver las novedades.",
                          "info"), True
        result = _decode_update(data_encoded)
        panel, n_new = build_result_panel(result, collapse_id=IDs.CLOSE_RESULT)
        return panel, (n_new == 0)

    # ------------------------------------------------------------------
    # 10) Descargar novedades y refrescar la app
    @app.callback(
        Output(IDs.UPDATES_STATUS, "children", allow_duplicate=True),
        Output(IDs.UPDATES_STORE, "data", allow_duplicate=True),
        Output(IDs.M_TOTAL, "children"),
        Output(IDs.M_DOCS, "children"),
        Output(IDs.M_CATS, "children"),
        Input(IDs.DOWNLOAD_NEW, "n_clicks"),
        State(IDs.UPDATES_STORE, "data"),
        prevent_initial_call=True,
    )
    def download_new(n, data_encoded):
        if not n:
            raise dash.exceptions.PreventUpdate
        result = _decode_update(data_encoded) or {}
        verifier = UpdateVerifier(data)
        res = verifier.scrape_new(result.get("new", []))
        stats = data.stats()
        status = (f"{res['msg']} Ahora hay {stats['total']:,} registros.")
        return (status, data_encoded,
                _fmt(stats["total"]),
                _fmt(stats["documentos"]),
                _fmt(stats["categorias"]))

    # ------------------------------------------------------------------
    # 11) Minimizar/cerrar el panel: "Comprobar" lo abre, la X lo cierra
    @app.callback(
        Output(IDs.UPDATES_RESULT, "is_open"),
        Input(IDs.CHECK_BTN, "n_clicks"),
        Input(IDs.CLOSE_RESULT, "n_clicks"),
    )
    def toggle_updates(check_n, close_n):
        triggered = dash.callback_context.triggered_id
        if triggered == IDs.CLOSE_RESULT:
            return False
        if triggered == IDs.CHECK_BTN:
            return True
        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 12) Asistente: procesar pregunta (botón, Enter o sugerencia guardada)
    @app.callback(
        Output(IDs.ASSISTANT_STORE, "data"),
        Output(IDs.ASSISTANT_INPUT, "value"),
        Input(IDs.ASSISTANT_SEND, "n_clicks"),
        Input(IDs.ASSISTANT_INPUT, "n_submit"),
        Input(IDs.ASSISTANT_QUESTION, "data"),
        State(IDs.ASSISTANT_INPUT, "value"),
        State(IDs.ASSISTANT_STORE, "data"),
        prevent_initial_call=True,
    )
    def assistant_ask(send_clicks, n_submit, question_sugg, input_value, history):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        trig = ctx.triggered_id
        if trig == IDs.ASSISTANT_QUESTION:
            question = (question_sugg or "").strip()
        elif trig in (IDs.ASSISTANT_SEND, IDs.ASSISTANT_INPUT):
            question = (input_value or "").strip()
        else:
            raise dash.exceptions.PreventUpdate

        if not question:
            raise dash.exceptions.PreventUpdate

        history = list(history or [])
        history.append({"role": "user", "content": question})
        try:
            # Pasar historial reciente para que la IA entienda el contexto de la conversación
            result = _assistant.answer(question, history=history[:-1])
            # Guardar solo la metadata requerida por los botones de la interfaz,
            # evitando saturar la memoria del servidor y el Store del cliente con textos crudos de PDFs.
            clean_sources = []
            for s in (result.get("sources") or []):
                clean_sources.append({
                    "url": s.get("url", ""),
                    "title": s.get("title") or "",
                    "category": s.get("category") or "",
                    "publish_date": s.get("publish_date") or "",
                    "docs_read": s.get("docs_read", 0),
                    "documents": s.get("documents", [])[:3],
                    "images": s.get("images", [])[:2],
                })

            history.append({
                "role": "assistant",
                "content": result["answer"],
                "sources": clean_sources,
                "used_ai": bool(result.get("used_ai")),
            })
        except Exception as exc:
            history.append({
                "role": "assistant",
                "content": f"⚠️ Ocurrió un error al consultar: {exc}",
                "sources": [],
            })
        history = history[-20:]
        return history, ""

    # ------------------------------------------------------------------
    # 12c) Overlay de carga a pantalla completa mientras el asistente procesa.
    # Se ejecuta EN EL NAVEGADOR (clientside), así que aparece al instante al
    # enviar la pregunta, y se oculta cuando llega la respuesta (el store del
    # chat se actualiza al terminar el callback lento).
    app.clientside_callback(
        """
        function(send_clicks, n_submit, question, hist, input_value, ctx) {
            const base = {
                "display": "none",
                "position": "fixed",
                "top": "0", "left": "0",
                "width": "100vw", "height": "100vh",
                "background": "rgba(8, 30, 63, 0.85)",
                "backdropFilter": "blur(8px)",
                "WebkitBackdropFilter": "blur(8px)",
                "zIndex": "9999",
                "alignItems": "center",
                "justifyContent": "center"
            };
            const triggered = (ctx && ctx.triggered) ? ctx.triggered : [];
            if (triggered.length === 0) return base;
            const prop = triggered[0].prop_id || "";

            const isQuestion = prop.indexOf("assistant-question.data") >= 0;
            const isSend = prop.indexOf("assistant-send.n_clicks") >= 0
                        || prop.indexOf("assistant-input.n_submit") >= 0;

            // Por sugerencia (chip) o por botón/Enter con texto escrito -> mostrar
            if (isQuestion) { base["display"] = "flex"; return base; }
            if (isSend && input_value && String(input_value).trim() !== "") {
                base["display"] = "flex"; return base;
            }
            // La respuesta llegó (se actualizó el historial del chat) -> ocultar
            return base;
        }
        """,
        Output(IDs.LOADING_OVERLAY, "style"),
        Input(IDs.ASSISTANT_SEND, "n_clicks"),
        Input(IDs.ASSISTANT_INPUT, "n_submit"),
        Input(IDs.ASSISTANT_QUESTION, "data"),
        Input(IDs.ASSISTANT_STORE, "data"),
        State(IDs.ASSISTANT_INPUT, "value"),
        prevent_initial_call=True,
    )

    # ------------------------------------------------------------------
    # 12b) Asistente: al pulsar una sugerencia, la guarda como pregunta
    @app.callback(
        Output(IDs.ASSISTANT_QUESTION, "data"),
        Input({"type": "assistant-sugg", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def assistant_suggestion(sugg_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == "assistant-sugg":
            return trig.get("index")
        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 13) Asistente de IA: renderiza el historial del chat
    @app.callback(
        Output(IDs.ASSISTANT_CHAT, "children"),
        Output("assistant-ai-status", "children"),
        Input(IDs.ASSISTANT_STORE, "data"),
    )
    def render_assistant(history):
        history = list(history or [])
        from .assistant import AI_PROVIDER, GEMINI_MODEL_LABEL, GROQ_MODEL_LABEL
        if AI_PROVIDER == "gemini":
            ai_note = f"IA conectada · {GEMINI_MODEL_LABEL}"
        elif AI_PROVIDER == "groq":
            ai_note = "IA conectada · " + GROQ_MODEL_LABEL
        else:
            ai_note = "Modo local (sin clave API)"

        if not history:
            placeholder = _assistant_msg(
                "Hola 👋 Soy el asistente de FENALCO. Pregúntame sobre los datos: "
                "noticias, informes, eventos, jurídicos…", "assistant",
                msg_idx=-1)
            return placeholder, ai_note

        blocks = []
        # msg_idx se pasa para generar IDs de botón estables por mensaje.
        # Así Dash no los trata como componentes nuevos en cada re-render.
        for msg_idx, m in enumerate(history):
            if m["role"] == "user":
                blocks.append(_assistant_msg(m["content"], "user",
                                             msg_idx=msg_idx))
            else:
                blocks.append(_assistant_msg(m["content"], "assistant",
                                             m.get("sources", []),
                                             msg_idx=msg_idx))
        return blocks, ai_note



    # ------------------------------------------------------------------
    # 14) Abrir/cerrar el offcanvas del asistente
    @app.callback(
        Output(IDs.ASSISTANT_OC, "is_open"),
        Input(IDs.ASSISTANT_FAB, "n_clicks"),
        Input(IDs.ASSISTANT_OC_CLOSE, "n_clicks"),
        Input(IDs.DOC_MODAL_OPEN, "data"),   # cerrar al abrir una fuente
        State(IDs.ASSISTANT_OC, "is_open"),
        prevent_initial_call=True,
    )
    def toggle_assistant(fab, close, modal_payload, is_open):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.ASSISTANT_FAB:
            return True
        if trig == IDs.ASSISTANT_OC_CLOSE:
            return False
        # Si se abre el modal de una fuente y el offcanvas está abierto → cerrarlo
        if trig == IDs.DOC_MODAL_OPEN:
            if modal_payload and modal_payload.get("open") and is_open:
                return False
            raise dash.exceptions.PreventUpdate
        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 14b) Ocultar el botón flotante (FAB) cuando el panel del asistente está abierto
    app.clientside_callback(
        """
        function(isOpen) {
            if (isOpen) {
                return {"display": "none"};
            }
            return {
                "position": "fixed", "bottom": "22px", "right": "22px",
                "zIndex": 1100, "borderRadius": "2rem", "border": "none",
                "padding": "0.7rem 1.1rem", "fontWeight": "600",
                "background": "linear-gradient(90deg, #084a86, #0b5cab)",
                "color": "#fff"
            };
        }
        """,
        Output(IDs.ASSISTANT_FAB, "style"),
        Input(IDs.ASSISTANT_OC, "is_open"),
    )

    # ------------------------------------------------------------------
    # 15) Abrir el modal desde las fuentes del asistente o botones de artículo
    @app.callback(
        Output(IDs.DOC_MODAL_OPEN, "data"),
        Input({"type": "assistant-source", "index": dash.ALL}, "n_clicks"),
        Input({"type": "open-article-btn", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_modal_from_assistant(sugg_clicks, article_clicks):
        import time as _time
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        trig_id = ctx.triggered_id
        if not (isinstance(trig_id, dict) and trig_id.get("type") in ("assistant-source", "open-article-btn")):
            raise dash.exceptions.PreventUpdate

        # Verificar clic real (n_clicks > 0)
        clicked_val = next(
            (item.get("value") for item in ctx.triggered
             if item.get("value") and item["value"] > 0),
            None
        )
        if not clicked_val:
            raise dash.exceptions.PreventUpdate

        raw = trig_id.get("index", "") or ""
        # El index es "<msg_idx>_<src_idx>|<url>" o la URL directamente
        url = raw.split("|", 1)[-1] if "|" in str(raw) else raw
        if not url:
            raise dash.exceptions.PreventUpdate

        return {"url": url, "open": True, "ts": _time.time()}

    # ------------------------------------------------------------------
    # 15c) Abrir el modal desde el botón "Ver en lectura completa" del panel lateral
    @app.callback(
        Output(IDs.SELECTED_URL, "data"),
        Output(IDs.DOC_MODAL_OPEN, "data", allow_duplicate=True),
        Input(IDs.READ_FULL, "n_clicks"),
        State(IDs.SELECTED_URL, "data"),
        State(IDs.TABLE, "active_cell"),
        State(IDs.TABLE, "data"),
        prevent_initial_call=True,
    )
    def open_modal_from_read_full(read_full, selected_url, active_cell, page_data):
        import time as _time
        if not read_full:
            raise dash.exceptions.PreventUpdate
        url = None
        if active_cell and page_data and isinstance(active_cell, dict):
            row_idx = active_cell.get("row")
            if row_idx is not None and 0 <= row_idx < len(page_data):
                url = page_data[row_idx].get("url", "") or None
        if not url:
            url = selected_url
        if not url:
            raise dash.exceptions.PreventUpdate
        return url, {"url": url, "open": True, "ts": _time.time()}

    # ------------------------------------------------------------------
    # 15b) Llenar y abrir/cerrar el modal de lectura de documento
    @app.callback(
        Output(IDs.DOC_MODAL, "is_open"),
        Output(IDs.DOC_MODAL_BODY, "children"),
        Output(IDs.DOC_MODAL_TITLE, "children"),
        Input(IDs.DOC_MODAL_OPEN, "data"),
        Input(IDs.DOC_MODAL_OPEN + "-close", "n_clicks"),
        State(IDs.SUMM_STORE, "data"),
        prevent_initial_call=True,
    )
    def show_doc_modal(payload, close_clicks, summ_store):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        trig_id = ctx.triggered_id

        # Botón cerrar
        if trig_id == (IDs.DOC_MODAL_OPEN + "-close"):
            return False, dash.no_update, dash.no_update

        if not payload or not payload.get("url"):
            return False, dash.no_update, dash.no_update

        rec = data.record(payload["url"])
        if not rec:
            return False, dash.no_update, dash.no_update

        existing_summ = (summ_store or {}).get(payload["url"]) if isinstance(summ_store, dict) else None

        body = html.Div([
            html.A(rec.get("url", ""), href=rec.get("url", ""),
                   target="_blank", className="small text-break d-block mb-2"),
            build_detail(rec, is_modal=True, existing_summary=existing_summ),
        ])
        return True, body, rec.get("title") or "Documento"

    # ------------------------------------------------------------------
    # 15d) Abrir el modal de imagen extraída al pulsar una miniatura del asistente
    @app.callback(
        Output(IDs.FULLIMG_OPEN, "data"),
        Input({"type": "assistant-img", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_fullimg(img_clicks):
        import time as _time
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if not (isinstance(trig, dict) and trig.get("type") == "assistant-img"):
            raise dash.exceptions.PreventUpdate
        clicked = next((c for c in ctx.triggered
                        if c.get("value") and c["value"] > 0), None)
        if not clicked:
            raise dash.exceptions.PreventUpdate
        index = str(trig.get("index", ""))
        if "::IMG::" in index:
            # index = "<unique_index>::IMG::<k>::<src>"
            src = index.split("::IMG::", 1)[1].split("::", 1)[-1]
            if src:
                return {"src": src, "caption": "Imagen extraída del documento",
                        "ts": _time.time()}
        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 15e) Llenar y abrir/cerrar el modal de imagen completa
    @app.callback(
        Output(IDs.FULLIMG_MODAL, "is_open"),
        Output(IDs.FULLIMG_TITLE, "children"),
        Output(IDs.FULLIMG_BODY, "children"),
        Input(IDs.FULLIMG_OPEN, "data"),
        Input(IDs.FULLIMG_CLOSE, "n_clicks"),
        prevent_initial_call=True,
    )
    def show_fullimg(payload, close_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        if ctx.triggered_id == IDs.FULLIMG_CLOSE:
            return False, dash.no_update, dash.no_update
        if not payload or not payload.get("src"):
            return False, dash.no_update, dash.no_update
        caption = payload.get("caption") or "Imagen extraída del documento"
        body = html.Div([
            html.P(caption, className="text-muted text-center small"),
            html.Img(src=payload["src"], className="img-fluid",
                     style={"maxWidth": "100%", "maxHeight": "78vh",
                            "objectFit": "contain"}),
        ])
        return True, "Imagen extraída del documento", body

    # ------------------------------------------------------------------
    # 16) Control de apertura del modal de adjuntos
    @app.callback(
        Output(IDs.DOCS_MODAL, "is_open"),
        Input(IDs.CARD_DOCS, "n_clicks"),
        Input(IDs.DOCS_MODAL_CLOSE, "n_clicks"),
        Input(IDs.DOCS_FILTER_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_docs_modal(open_clicks, close_clicks, filter_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.CARD_DOCS and open_clicks:
            return True
        if trig in (IDs.DOCS_MODAL_CLOSE, IDs.DOCS_FILTER_BTN):
            return False
        raise dash.exceptions.PreventUpdate

    # 16b) Paginador del explorador de adjuntos
    @app.callback(
        Output(IDs.DOCS_PAGE, "data"),
        Input(IDs.DOCS_SEARCH, "value"),
        Input(IDs.DOCS_PREV, "n_clicks"),
        Input(IDs.DOCS_NEXT, "n_clicks"),
        State(IDs.DOCS_PAGE, "data"),
        prevent_initial_call=True,
    )
    def paginate_docs(search, prev_clicks, next_clicks, current_page):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.DOCS_SEARCH:
            return 0
        current_page = current_page or 0
        if trig == IDs.DOCS_PREV:
            return max(0, current_page - 1)
        if trig == IDs.DOCS_NEXT:
            return current_page + 1
        return 0

    # 16c) Renderizar lista de adjuntos
    @app.callback(
        Output(IDs.DOCS_CONTAINER, "children"),
        Output(IDs.DOCS_PAGE_INFO, "children"),
        Input(IDs.DOCS_MODAL, "is_open"),
        Input(IDs.DOCS_PAGE, "data"),
        Input(IDs.DOCS_SEARCH, "value"),
    )
    def render_docs(is_open, page, search):
        if not is_open:
            raise dash.exceptions.PreventUpdate
        docs = data.get_all_documents(search or "")
        total = len(docs)
        if total == 0:
            msg = "No se encontraron adjuntos coincidentes con la búsqueda." if search else "No hay adjuntos disponibles."
            return dbc.Alert(msg, color="warning"), "0 adjuntos encontrados"

        page_size = 15
        total_pages = max(1, math.ceil(total / page_size))
        page = max(0, min(page or 0, total_pages - 1))
        start_idx = page * page_size
        page_items = docs[start_idx : start_idx + page_size]

        items_ui = []
        for d in page_items:
            url = d.get("url", "")
            is_drive = "drive.google.com" in url or "docs.google.com" in url
            icon_cls = "bi bi-google text-danger" if is_drive else "bi bi-file-earmark-arrow-down text-primary"
            items_ui.append(
                dbc.Card(
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.I(className=f"{icon_cls} fs-4 me-3 mt-1"),
                                    html.Div([
                                        html.A(
                                            d["filename"],
                                            href=url,
                                            target="_blank",
                                            className="fw-bold text-decoration-none text-break fs-6",
                                            title="Abrir adjunto en pestaña nueva",
                                        ),
                                        html.Div([
                                            html.Span(d["article_title"], className="text-secondary small me-2"),
                                            dbc.Badge(d["category"], color="light", text_color="dark", className="me-1 small border"),
                                            dbc.Badge(d["date"], color="light", text_color="secondary", className="small") if d.get("date") else None,
                                        ], className="d-flex align-items-center flex-wrap mt-1"),
                                    ], className="flex-grow-1"),
                                ], className="d-flex align-items-start"),
                            ], md=8, lg=9),
                            dbc.Col([
                                dbc.ButtonGroup([
                                    dbc.Button(
                                        [html.I(className="bi bi-file-text me-1"), "Ver artículo"],
                                        id={"type": "open-article-btn", "index": d["article_url"]},
                                        color="outline-secondary",
                                        size="sm",
                                        n_clicks=0,
                                        title="Ver contenido del artículo completo",
                                    ),
                                    html.A(
                                        [html.I(className="bi bi-box-arrow-up-right me-1"), "Abrir"],
                                        href=url,
                                        target="_blank",
                                        className="btn btn-sm btn-primary",
                                    ),
                                ], size="sm", className="w-100 justify-content-end mt-2 mt-md-0"),
                            ], md=4, lg=3, className="text-md-end"),
                        ], className="align-items-center g-2"),
                    ], className="py-2 px-3"),
                    className="mb-2 doc-item-card shadow-none",
                )
            )

        info_text = f"Mostrando {start_idx + 1:,} - {min(start_idx + page_size, total):,} de {total:,} adjuntos · Página {page + 1} de {total_pages}"
        return html.Div(items_ui), info_text

    # ------------------------------------------------------------------
    # 17) Control de apertura de la galería de imágenes
    @app.callback(
        Output(IDs.IMGS_MODAL, "is_open"),
        Input(IDs.CARD_IMGS, "n_clicks"),
        Input(IDs.IMGS_MODAL_CLOSE, "n_clicks"),
        Input(IDs.IMGS_FILTER_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_imgs_modal(open_clicks, close_clicks, filter_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.CARD_IMGS and open_clicks:
            return True
        if trig in (IDs.IMGS_MODAL_CLOSE, IDs.IMGS_FILTER_BTN):
            return False
        raise dash.exceptions.PreventUpdate

    # 17b) Paginador de la galería de imágenes
    @app.callback(
        Output(IDs.IMGS_PAGE, "data"),
        Input(IDs.IMGS_SEARCH, "value"),
        Input(IDs.IMGS_PREV, "n_clicks"),
        Input(IDs.IMGS_NEXT, "n_clicks"),
        State(IDs.IMGS_PAGE, "data"),
        prevent_initial_call=True,
    )
    def paginate_imgs(search, prev_clicks, next_clicks, current_page):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.IMGS_SEARCH:
            return 0
        current_page = current_page or 0
        if trig == IDs.IMGS_PREV:
            return max(0, current_page - 1)
        if trig == IDs.IMGS_NEXT:
            return current_page + 1
        return 0

    # 17c) Renderizar cuadrícula de imágenes
    @app.callback(
        Output(IDs.IMGS_CONTAINER, "children"),
        Output(IDs.IMGS_PAGE_INFO, "children"),
        Input(IDs.IMGS_MODAL, "is_open"),
        Input(IDs.IMGS_PAGE, "data"),
        Input(IDs.IMGS_SEARCH, "value"),
    )
    def render_imgs(is_open, page, search):
        if not is_open:
            raise dash.exceptions.PreventUpdate
        imgs = data.get_all_images(search or "")
        total = len(imgs)
        if total == 0:
            msg = "No se encontraron imágenes coincidentes con la búsqueda." if search else "No hay imágenes disponibles."
            return dbc.Alert(msg, color="warning"), "0 imágenes encontradas"

        page_size = 12
        total_pages = max(1, math.ceil(total / page_size))
        page = max(0, min(page or 0, total_pages - 1))
        start_idx = page * page_size
        page_items = imgs[start_idx : start_idx + page_size]

        cols = []
        for im in page_items:
            src = im["src"]
            cols.append(
                dbc.Col(
                    dbc.Card([
                        html.A(
                            html.Div(
                                html.Img(src=src, className="gallery-thumb-img", alt=im["article_title"]),
                                className="gallery-thumb-container",
                            ),
                            href=src,
                            target="_blank",
                            title="Haz clic para ver la imagen en tamaño completo",
                        ),
                        dbc.CardBody([
                            html.Div([
                                dbc.Badge(im["category"], color="light", text_color="primary", className="border me-1 small"),
                                html.Span(im["date"], className="small text-muted") if im.get("date") else None,
                            ], className="d-flex align-items-center justify-content-between mb-1"),
                            html.P(
                                im["article_title"],
                                className="small fw-semibold text-truncate mb-2",
                                title=im["article_title"],
                            ),
                            dbc.Button(
                                [html.I(className="bi bi-file-text me-1"), "Ver publicación"],
                                id={"type": "open-article-btn", "index": im["article_url"]},
                                color="outline-primary",
                                size="sm",
                                className="w-100",
                                n_clicks=0,
                            ),
                        ], className="p-2"),
                    ], className="gallery-img-card h-100 shadow-none"),
                    xs=12, sm=6, md=4, lg=3,
                    className="mb-3",
                )
            )

        info_text = f"Mostrando {start_idx + 1:,} - {min(start_idx + page_size, total):,} de {total:,} imágenes · Página {page + 1} de {total_pages}"
        return dbc.Row(cols, className="g-3"), info_text

    # ------------------------------------------------------------------
    # 18) Control de apertura del catálogo de categorías
    @app.callback(
        Output(IDs.CATS_MODAL, "is_open"),
        Input(IDs.CARD_CATS, "n_clicks"),
        Input(IDs.CATS_MODAL_CLOSE, "n_clicks"),
        Input({"type": "cat-select-btn", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_cats_modal(open_clicks, close_clicks, select_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig == IDs.CARD_CATS and open_clicks:
            return True
        if trig == IDs.CATS_MODAL_CLOSE:
            return False
        if isinstance(trig, dict) and trig.get("type") == "cat-select-btn":
            clicked_val = next((item.get("value") for item in ctx.triggered if item.get("value")), None)
            if clicked_val:
                return False
        raise dash.exceptions.PreventUpdate

    # 18b) Renderizar catálogo de categorías
    @app.callback(
        Output(IDs.CATS_CONTAINER, "children"),
        Input(IDs.CATS_MODAL, "is_open"),
        Input(IDs.CATS_SEARCH, "value"),
    )
    def render_cats(is_open, search):
        if not is_open:
            raise dash.exceptions.PreventUpdate
        cats = data.get_category_stats(search or "")
        if not cats:
            return dbc.Alert("No se encontraron categorías.", color="warning")

        cards = []
        for c in cats:
            name = c["category"]
            cards.append(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody([
                            html.Div([
                                html.Span(name, className="fw-bold text-dark text-break fs-6"),
                            ], className="mb-2"),
                            html.Div([
                                dbc.Badge(f"{c['records']:,} registros", color="primary", className="me-1 mb-1 small"),
                                dbc.Badge(f"{c['documents']:,} adjuntos", color="secondary", className="me-1 mb-1 small") if c["documents"] > 0 else None,
                                dbc.Badge(f"{c['images']:,} imágenes", color="info", className="mb-1 small") if c["images"] > 0 else None,
                            ], className="d-flex flex-wrap mb-2"),
                            dbc.Button(
                                [html.I(className="bi bi-funnel me-1"), "Filtrar por esta categoría"],
                                id={"type": "cat-select-btn", "index": name},
                                color="outline-primary",
                                size="sm",
                                className="w-100",
                                n_clicks=0,
                            ),
                        ], className="p-3"),
                        className="cat-pill-card h-100 shadow-none",
                    ),
                    xs=12, sm=6, md=4,
                    className="mb-3",
                )
            )
        return dbc.Row(cards, className="g-3")

    # ------------------------------------------------------------------
    # 18c) Control de apertura del modal Buscador de Cifras
    @app.callback(
        Output(IDs.CIFRAS_MODAL, "is_open"),
        Input(IDs.CIFRAS_OPEN_BTN, "n_clicks"),
        Input(IDs.CIFRAS_CARD, "n_clicks"),
        Input(IDs.CIFRAS_MODAL_CLOSE, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_cifras_modal(btn_clicks, card_clicks, close_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if trig in (IDs.CIFRAS_OPEN_BTN, IDs.CIFRAS_CARD) and (btn_clicks or card_clicks):
            return True
        if trig == IDs.CIFRAS_MODAL_CLOSE:
            return False
        raise dash.exceptions.PreventUpdate

    # 18d) Chips sugeridos de cifras
    @app.callback(
        Output(IDs.CIFRAS_INPUT, "value"),
        Input({"type": "cifra-chip-btn", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def set_cifra_from_chip(n_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trig = ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == "cifra-chip-btn":
            val = trig.get("index")
            clicked = next((item.get("value") for item in ctx.triggered if item.get("value")), None)
            if clicked and val:
                return val
        raise dash.exceptions.PreventUpdate

    # 18e) Paginación del buscador de cifras
    # 18f) Búsqueda unificada y atómica de cifras con rastreo automático en Google Drive
    @app.callback(
        Output(IDs.CIFRAS_CONTAINER, "children"),
        Output(IDs.CIFRAS_COUNT_INFO, "children"),
        Output(IDs.CIFRAS_PAGE_INFO, "children"),
        Output(IDs.CIFRAS_PAGE, "data"),
        Input(IDs.CIFRAS_MODAL, "is_open"),
        Input(IDs.CIFRAS_INPUT, "value"),
        Input(IDs.CIFRAS_KEYWORDS, "value"),
        Input(IDs.CIFRAS_SEARCH_BTN, "n_clicks"),
        Input(IDs.CIFRAS_ORIGIN, "value"),
        Input(IDs.CIFRAS_PREV, "n_clicks"),
        Input(IDs.CIFRAS_NEXT, "n_clicks"),
        State(IDs.CIFRAS_PAGE, "data"),
    )
    def render_cifras_search(is_open, query, keywords_str, search_clicks, origin_filter, prev_clicks, next_clicks, current_page):
        if not is_open:
            raise dash.exceptions.PreventUpdate

        ctx = dash.callback_context
        trig = ctx.triggered_id if ctx.triggered else None

        # Determinar página de forma atómica sin race conditions
        page = current_page or 0
        if trig == IDs.CIFRAS_PREV:
            page = max(0, page - 1)
        elif trig == IDs.CIFRAS_NEXT:
            page = page + 1
        elif trig in (IDs.CIFRAS_INPUT, IDs.CIFRAS_KEYWORDS, IDs.CIFRAS_SEARCH_BTN, IDs.CIFRAS_ORIGIN, IDs.CIFRAS_MODAL):
            page = 0

        from .cifras_search import search_cifras

        q = (query or "").strip()
        if not q:
            empty_msg = html.Div([
                html.Div([
                    html.I(className="bi bi-percent fs-1 text-primary opacity-50 mb-2"),
                    html.H5("Escribe un porcentaje o cifra para buscar", className="fw-semibold text-secondary"),
                    html.P("El buscador rastreará de forma exacta en los 4.000 artículos, en el texto digital de los PDFs y en las tablas/gráficas escaneadas.",
                           className="text-muted mb-3", style={"maxWidth": "540px", "margin": "0 auto"}),
                ], className="text-center py-5"),
            ])
            return empty_msg, None, "", 0

        # Si el usuario especificó palabras clave, ejecutar automáticamente el rastreo inteligente sobre Drive
        kws = [k.strip() for k in (keywords_str or "").split(",") if k.strip()]
        crawl_stats = None
        if kws:
            try:
                from .smart_cifras_crawler import SmartCifrasCrawler
                import concurrent.futures as _cf
                crawler = SmartCifrasCrawler(data)
                # El crawl se ejecuta en un hilo aparte con timeout de 60s para no bloquear
                # el worker de Gunicorn y evitar el 502 en Render.
                # OCR desactivado en el crawl interactivo: los PDFs ya tienen texto digital
                # en doc_cache; el OCR se aplica solo desde pre_cache_attachments.
                def _run_crawl():
                    return crawler.crawl_and_inspect(
                        cifra_query=q,
                        keywords=kws,
                        max_downloads=4,   # máx 4 descargas efímeras (era 8)
                        enable_ocr=False,  # sin OCR en tiempo real → evita timeout
                    )
                with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                    _fut = _pool.submit(_run_crawl)
                    try:
                        crawl_stats = _fut.result(timeout=60)
                    except _cf.TimeoutError:
                        pass  # Si supera 60s, continúa sin el crawl (no 502)
            except Exception as e:
                pass

        data_res = search_cifras(
            data,
            q,
            keywords_filter=kws,
            origin_filter=origin_filter or "all",
            max_results=300
        )
        total = data_res["total_matches"]
        results = data_res["results"]

        # Resumen superior
        summary_badges = [
            dbc.Badge(f"{total:,} coincidencias en total", color="primary", className="me-2 fs-6 px-3 py-2"),
            dbc.Badge(f"📰 {data_res['count_articulos']:,} en artículos", color="light", text_color="dark", className="me-1 border"),
            dbc.Badge(f"📄 {data_res['count_documentos']:,} en PDFs", color="light", text_color="dark", className="me-1 border"),
            dbc.Badge(f"📊 {data_res['count_graficas']:,} en gráficas/tablas (OCR)", color="light", text_color="dark", className="border"),
        ]

        sub_msg_parts = [
            f"Búsqueda exacta: {data_res['label']}",
            f"Cobertura: {data_res['docs_cached_count']} PDFs indexados de {data_res['docs_total_count']} totales en BD",
        ]
        if crawl_stats and crawl_stats.get("candidates_found", 0) > 0:
            sub_msg_parts.append(
                f"⚡ Filtro automático aplicado: {crawl_stats['candidates_found']} candidatos en Drive evaluados y limpiados"
            )

        info_header = html.Div([
            html.Div(summary_badges, className="d-flex flex-wrap align-items-center mb-2"),
            html.P(" · ".join(sub_msg_parts), className="small text-muted mb-0"),
        ], className="p-3 bg-light rounded border mb-3")

        if total == 0:
            no_results = dbc.Alert([
                html.I(className="bi bi-info-circle me-2"),
                f"No se encontró la cifra «{q}» en los registros ni en los documentos analizados.",
            ], color="warning")
            return no_results, info_header, "0 resultados", 0

        page_size = 10
        total_pages = max(1, math.ceil(total / page_size))
        current_page = max(0, min(page or 0, total_pages - 1))
        start_idx = current_page * page_size
        page_items = results[start_idx : start_idx + page_size]

        cards = []
        for idx, item in enumerate(page_items, start=start_idx + 1):
            # Badge de origen
            origin_badge = dbc.Badge([
                html.I(className=f"bi bi-{item['icon']} me-1"),
                item["origin_label"]
            ], color=item["badge_color"], className="me-2")

            cat_badge = dbc.Badge(item["category"], color="light", text_color="secondary", className="border me-2")
            date_badge = html.Span(item["date"], className="small text-muted") if item.get("date") else None

            # Imagen de gráfica si aplica
            img_element = None
            if item.get("image"):
                im = item["image"]
                img_element = html.Div([
                    html.Img(src=im["src"], className="assistant-doc-img me-3", style={"maxHeight": "95px"}),
                    html.Div([
                        html.Span(im["caption"], className="small fw-semibold text-secondary d-block"),
                        dbc.Button(
                            [html.I(className="bi bi-arrows-fullscreen me-1"), "Ver gráfica ampliada"],
                            id={"type": "doc-img-thumb", "index": f"{im['src']}|{im['caption']}"},
                            size="sm",
                            color="outline-warning",
                            className="mt-1 py-0 px-2 small shadow-none",
                            n_clicks=0,
                        ),
                    ]),
                ], className="d-flex align-items-center mb-2 p-2 bg-light rounded border")

            # Botones de acción
            actions = []
            if item.get("url"):
                actions.append(
                    dbc.Button(
                        [html.I(className="bi bi-eye me-1"), "Ver publicación"],
                        id={"type": "open-article-btn", "index": item["url"]},
                        color="outline-primary",
                        size="sm",
                        className="me-2",
                        n_clicks=0,
                    )
                )
            if item.get("drive_url"):
                actions.append(
                    html.A(
                        [html.I(className="bi bi-google me-1 text-danger"), "Abrir PDF"],
                        href=item["drive_url"],
                        target="_blank",
                        className="btn btn-sm btn-outline-secondary me-2",
                    )
                )

            card = dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Span(f"#{idx}", className="fw-bold text-muted me-2 small"),
                        origin_badge,
                        cat_badge,
                        html.Div(date_badge, className="ms-auto") if date_badge else None,
                    ], className="d-flex align-items-center mb-1"),
                    html.H6(item["title"], className="fw-bold text-primary mt-1 mb-2 text-break"),
                    dcc.Markdown(item["snippet"], dangerously_allow_html=True, className="cifra-snippet-text mb-2"),
                    img_element,
                    html.Div(actions, className="d-flex flex-wrap mt-2"),
                ], className="p-3"),
            ], className="mb-2 shadow-sm border-0 cifra-result-card")
            cards.append(card)

        page_info_text = f"Mostrando {start_idx + 1:,} - {min(start_idx + page_size, total):,} de {total:,} coincidencias · Página {current_page + 1} de {total_pages}"
        return html.Div(cards), info_header, page_info_text, current_page

    def _generate_record_summary(url: str):
        if not url:
            return None, "No hay ningún registro seleccionado."
        rec = data.record(url)
        if not rec:
            return None, "Registro no encontrado en la base de datos."

        text = rec.get("content_text") or ""
        title = rec.get("title") or ""

        # Obtener textos de documentos adjuntos de Google Drive
        doc_texts = []
        from .drive_reader import clean_spaced_name, extract_drive_id, drive_reader as _dr
        for d in (rec.get("documents") or [])[:5]:
            u = d.get("url") or ""
            did = extract_drive_id(u)
            if did:
                cached = _dr.get_cached_text(did)
                if cached:
                    doc_texts.append({
                        "filename": clean_spaced_name(d.get("filename") or "") or "Documento",
                        "text": cached,
                    })

        summary = _assistant.summarize(text, title=title, doc_texts=doc_texts)
        return summary, None

    # ------------------------------------------------------------------
    # 19a) Resumen IA desde el panel lateral de detalles
    @app.callback(
        Output(IDs.SUMM_OUT, "children"),
        Output(IDs.SUMM_STORE, "data", allow_duplicate=True),
        Input(IDs.SUMM_BTN, "n_clicks"),
        State(IDs.SELECTED_URL, "data"),
        State(IDs.TABLE, "active_cell"),
        State(IDs.TABLE, "data"),
        State(IDs.SUMM_STORE, "data"),
        prevent_initial_call=True,
    )
    def summarize_record_panel(n_clicks, selected_url, active_cell, page_data, summ_store):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        url = None
        if active_cell and page_data and isinstance(active_cell, dict):
            row_idx = active_cell.get("row")
            if row_idx is not None and 0 <= row_idx < len(page_data):
                url = page_data[row_idx].get("url") or None
        if not url:
            url = selected_url
        if not url:
            return dbc.Alert("No hay ningún registro seleccionado.", color="warning", className="py-2 small"), dash.no_update

        summary, err = _generate_record_summary(url)
        if err:
            return dbc.Alert(err, color="warning", className="py-2 small"), dash.no_update

        store_data = dict(summ_store or {})
        store_data[url] = summary
        from .detail import render_summary_card
        return render_summary_card(summary), store_data

    # ------------------------------------------------------------------
    # 19b) Resumen IA desde el modal de lectura completa
    @app.callback(
        Output(IDs.SUMM_MODAL_OUT, "children"),
        Output(IDs.SUMM_STORE, "data", allow_duplicate=True),
        Input(IDs.SUMM_MODAL_BTN, "n_clicks"),
        State(IDs.DOC_MODAL_OPEN, "data"),
        State(IDs.SELECTED_URL, "data"),
        State(IDs.SUMM_STORE, "data"),
        prevent_initial_call=True,
    )
    def summarize_record_modal(n_clicks, modal_open_data, selected_url, summ_store):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        url = None
        if modal_open_data and isinstance(modal_open_data, dict):
            url = modal_open_data.get("url")
        if not url:
            url = selected_url
        if not url:
            return dbc.Alert("No hay ningún registro seleccionado.", color="warning", className="py-2 small"), dash.no_update

        summary, err = _generate_record_summary(url)
        if err:
            return dbc.Alert(err, color="warning", className="py-2 small"), dash.no_update

        store_data = dict(summ_store or {})
        store_data[url] = summary
        from .detail import render_summary_card
        return render_summary_card(summary), store_data


def _alert(message, color):
    import dash_bootstrap_components as _dbc
    return _dbc.Alert(message, color=color)


def _encode_update(result: dict) -> str:
    """Codifica el resultado del chequeo para guardarlo en el Store."""
    import json
    return json.dumps(result, ensure_ascii=False)


def _decode_update(encoded) -> dict | None:
    import json
    if not encoded:
        return None
    try:
        return json.loads(encoded)
    except Exception:
        return None


def _fmt(n: int) -> str:
    return f"{n:,}"

def _ai_answer_components(content, sources=None, msg_idx=0):
    """Convierte la respuesta de la IA en Markdown limpio y sin enlaces rotos."""
    from dash import dcc as _dcc
    from bs4 import BeautifulSoup
    import re as _re
    import html as _html_unescape

    # 1) Eliminar cualquier enlace <a href="...">texto</a> dejando solo el texto
    content = _re.sub(r"<a[^>]*>(.*?)</a>", r"\1", content, flags=_re.IGNORECASE | _re.DOTALL)
    content = _re.sub(r"<a[^>]*/>", "", content, flags=_re.IGNORECASE)

    # 2) Eliminar enlaces markdown vacíos, falsos enlaces devtunnels o referencias que recargan la página
    content = _re.sub(r"\[([^\]]+)\]\((?:#|https?://[^\)]*devtunnels\.ms[^\)]*|https?://localhost[^\)]*|https?://127\.0\.0\.1[^\)]*|\s*)\)", r"\1", content, flags=_re.IGNORECASE)
    content = _re.sub(r"\[([^\]]+)\]\(\s*\)", r"\1", content)
    # Reemplazar sintaxis de definición de enlaces de Markdown (ej. "[Origen del dato]:") para evitar navegación vacía
    content = _re.sub(r"^\s*\[([^\]]+)\]:\s*", r"**\1:** ", content, flags=_re.MULTILINE)
    content = _re.sub(r"\[(Página\s+\d+\s+de\s+\d+)\]", r"\1", content, flags=_re.IGNORECASE)
    content = _re.sub(r"\[(Origen[^\]]*)\]", r"**\1**", content, flags=_re.IGNORECASE)

    # 3) Convertir tablas HTML a Markdown
    def _table_to_md(m):
        frag = m.group(0)
        try:
            soup = BeautifulSoup(frag, "html.parser")
        except Exception:
            return frag
        rows = []
        for tr in soup.find_all("tr"):
            cells = []
            for c in tr.find_all(["td", "th"]):
                txt = _html_unescape.unescape(c.get_text(" ", strip=True))
                txt = _re.sub(r"\s+", " ", txt).strip()
                cells.append(txt)
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        out = ["| " + " | ".join(rows[0]) + " |"]
        out.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
        for r in rows[1:]:
            out.append("| " + " | ".join(r) + " |")
        return "\n\n" + "\n".join(out) + "\n\n"

    content = _re.sub(
        r"<table[\s\S]*?</table>|<tbody[\s\S]*?</tbody>|<thead[\s\S]*?</thead>",
        _table_to_md, content, flags=_re.IGNORECASE)

    # 4) Decodificar entidades HTML
    content = _html_unescape.unescape(content)

    # 5) Eliminar etiquetas HTML sobrantes
    content = _re.sub(
        r"</?(?:table|tbody|thead|tfoot|tr|td|th|strong|b|em|i|p|br|ul|ol|li"
        r"|h1|h2|h3|h4|div|span|a)[^>]*>", "", content,
        flags=_re.IGNORECASE)
    content = _re.sub(r"<[^>]+>", "", content)

    # Compactar espacios
    content = _re.sub(r"[ \t]+", " ", content)
    content = _re.sub(r" ?\n ?", "\n", content).strip()

    return [_dcc.Markdown(content, dangerously_allow_html=False,
                          className="assistant-bubble ai mb-1")]


def _assistant_msg(content, role, sources=None, msg_idx=0):
    from dash import html as _html, dcc as _dcc

    if role == "user":
        return _html.Div([
            _html.Div("Tú", className="fw-bold small text-secondary mb-1"),
            _html.Div(content, className="assistant-bubble user"),
        ], className="mb-2")

    # Mensaje del asistente con posibles fuentes.
    # Se procesa el contenido para que las tablas se vean bien y las citas
    # [N] se vuelvan botones que abren el documento (sin recargar la página).
    body_children = _ai_answer_components(content, sources or [], msg_idx=msg_idx)
    if not body_children:
        body_children = [_dcc.Markdown(content,
                                       className="assistant-bubble ai mb-1")]

    children = [
        _html.Div("Asistente", className="fw-bold small text-primary mb-1"),
        *body_children,
    ]
    if sources:
        children.append(_html.Div(
            _html_to_sources(sources, msg_idx=msg_idx),
            className="assistant-sources mt-2"
        ))

    return _html.Div(children, className="mb-3")


def _html_doc_images(images, unique_index, max_show=6):
    """Renderiza miniaturas de las imágenes extraídas de un documento (gráficas).

    Cada miniatura es un botón con id {'type':'assistant-img', ...}; al pulsarlo
    se abre el modal de imagen completa.
    """
    from dash import html as _html

    out = []
    for k, img in enumerate(images[:max_show]):
        src = img.get("src") or ""
        caption = img.get("caption") or ""
        if not src:
            continue
        index = f"{unique_index}::IMG::{k}::{src}"
        out.append(
            _html.Button(
                _html.Img(
                    src=src,
                    className="assistant-doc-img",
                    alt=caption or "Imagen extraída",
                ),
                id={"type": "assistant-img", "index": index},
                n_clicks=0,
                className="assistant-img-btn p-0 border-0 bg-transparent me-2 mb-1",
                title=f"{caption or 'Imagen extraída'} — clic para ver la gráfica completa",
            )
        )
    if out:
        header = _html.Div([
            _html.Span("📊 Imágenes extraídas del documento (clic para ver completa):",
                       className="fw-semibold small text-muted"),
        ], className="mt-1 mb-1")
        return [header, _html.Div(out, className="d-flex flex-wrap my-1")]
    return out


def _html_to_sources(sources, msg_idx=0):
    """Genera los botones de todas las fuentes coincidentes del asistente.

    Usa msg_idx + src_idx para IDs estables: el mismo mensaje siempre produce
    los mismos IDs, evitando que Dash los trate como nuevos en cada re-render.
    """
    from dash import html as _html
    import dash_bootstrap_components as _dbc

    out = []
    n_sources = len(sources)
    for src_idx, s in enumerate(sources):
        url = s.get("url", "") or ""
        title = s.get("title") or url
        unique_index = f"{msg_idx}_{src_idx}|{url}"

        badges = []
        if s.get("category"):
            badges.append(_dbc.Badge(s["category"], color="light", text_color="dark", className="me-1 border small"))
        if s.get("publish_date"):
            badges.append(_dbc.Badge(s["publish_date"], color="light", text_color="secondary", className="me-1 small"))

        docs_count = len(s.get("documents") or [])
        docs_read = s.get("docs_read", 0)
        if docs_read > 0:
            badges.append(_dbc.Badge(f"📄 {docs_read} doc(s) de Drive analizado(s)", color="success", className="small"))
        elif docs_count > 0:
            badges.append(_dbc.Badge(f"📎 {docs_count} adjunto(s)", color="info", className="small"))

        out.append(_html.Div([
            _html.Button(
                [
                    _html.Div([
                        _html.I(className="bi bi-file-earmark-text me-1 text-primary"),
                        _html.Span(f"[{src_idx + 1}] {title}", className="fw-semibold text-break"),
                    ], className="d-flex align-items-center flex-wrap"),
                    _html.Div(badges, className="mt-1 d-flex flex-wrap align-items-center") if badges else None,
                ],
                id={"type": "assistant-source", "index": unique_index},
                n_clicks=0,
                className="btn btn-sm btn-outline-primary w-100 text-start mb-1 assistant-source-btn shadow-none",
                title="Abrir el detalle de este documento en pantalla",
            ),
        ] + _html_doc_images(s.get("images") or [], unique_index),
            className="mb-1",
        ))

    sources_container = _html.Div(
        out,
        style={
            "maxHeight": "240px",
            "overflowY": "auto",
            "paddingRight": "4px",
        } if n_sources > 4 else {}
    )

    header = _html.Div([
        _html.Span(f"Fuentes ({n_sources} coincidencia{'s' if n_sources != 1 else ''}):",
                   className="fw-bold small text-muted me-1"),
    ], className="mb-1")

    return [header, sources_container]


