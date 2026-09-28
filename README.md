# Scraper de FENALCO (fenalco.com.co)

Programa en Python que extrae **todos los datos públicos** del sitio web de la
Federación Nacional de Comerciantes Empresarios (FENALCO):
<https://www.fenalco.com.co/>

## ¿Qué se extrae?

El sitio corre sobre la plataforma **Odoo**. La "tabla de contenidos" oficial
es su `sitemap.xml`, que contiene **~3975 URLs**. El scraper recorre cada una y
extrae su contenido en forma estructurada:

| Tipo       | Cantidad | Descripción                                             |
|------------|----------|---------------------------------------------------------|
| Blog posts | ~3756    | Noticias, NotiJurídicos, informes económicos/gremiales  |
| CMS        | ~106     | El Gremio, Formación, Seccionales, Sectores, Servicios… |
| Eventos    | ~87      | Webinars, cursos, talleres, ferias                      |
| Otros      | (opcional)| Auxiliares que requieren login (perfil, shop, helpdesk) |

Para cada página se guarda:
- `url`, `title` (título), `subtitle` (metadescripción)
- `category` (categoría del blog o sección del sitio)
- `publish_date`, `lastmod`
- `content_blocks`: contenido en bloques estructurados (encabezados, párrafos,
  listas, tablas, citas, imágenes) con su jerarquía
- `content_text`: texto plano completo
- `images`: URLs de las imágenes
- `documents`: enlaces a documentos descargables y **documentos embebidos**
  (PDF, adjuntos de Odoo, Google Drive, OneDrive, Dropbox…)
- `links`: enlaces internos/externos del texto

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias: `requests`, `beautifulsoup4`, `lxml`.

## Uso

```bash
# Scrapear todo el contenido público
python run.py

# Prueba rápida con 20 páginas
python run.py --limit 20

# Solo un tipo de página
python run.py --only cms
python run.py --only event
python run.py --only blog

# Ajustar concurrencia / cortesía hacia el servidor
python run.py --workers 4 --delay 0.5

# Incluir páginas auxiliares (perfil, shop, helpdesk, listados del blog)
python run.py --include-aux

# Reintentar desde cero (ignora el checkpoint de páginas ya hechas)
python run.py --no-resume
```

El scraper es **reanudable**: guarda un checkpoint en `output/.done.txt` y los
resultados (JSONL) en tiempo real, así que si se interrumpe, al volver a
ejecutar continúa donde quedó.

## Exportar resultados

Tras el scrape, genera archivos finales legibles:

```bash
python export.py
```

Esto crea en `output/`:

- `fenalco_all.json` — todos los registros en un solo JSON
- `fenalco_index.csv` — índice plano (url, tipo, categoría, título, fechas…)
- `markdown/<categoria>.md` — el contenido completo organizado por categoría
- `resumen.json` — estadísticas y rutas de los archivos generados

## Interfaz gráfica (consultar y ordenar los datos)

Además de extraer, hay una **aplicación web interactiva** para presentar,
ordenar, filtrar y consultar los datos de forma visual y amigable:

```bash
python app.py                 # abre http://127.0.0.1:8050
python app.py --port 8051     # puerto personalizado
```

Características de la interfaz:

- **Panel de métricas**: total de registros, posts, CMS, eventos, adjuntos,
  imágenes, categorías y caracteres.
- **Búsqueda libre** en título, subtítulo, categoría, enlace y cuerpo del texto.
- **Filtros combinables**: tipo de contenido (blog/CMS/evento), categoría y
  rango de fechas.
- **Tabla ordenable y paginable** (multi-orden con clic en los encabezados,
  filas por página configurable).
- **Panel de detalle**: al hacer clic en una fila se muestra el contenido
  completo del registro (texto enriquecido, documentos adjuntos e imágenes),
  con un botón **«Ver en lectura completa»**.
- **Apartado exclusivo de lectura**: cada documento también se abre en un
  **modal grande centrado** (lectura cómoda, sin que el asistente lo tape).
  Se abre al pulsar ese botón o cualquier **fuente** que indique el asistente
  de IA — sin recargar la página, solo se muestra el documento.
- **Exportación integrada**: descendes a CSV todo el conjunto filtrado o el
  JSON de un registro concreto.
- **Asistente de IA** («Asistente FENALCO»): chat **flotante** (botón en la
  esquina inferior derecha) que busca en los datos y responde en lenguaje
  natural (¿qué dice FENALCO del salario mínimo?, ¿cuáles son los informes de
  vehículos eléctricos?, ¿qué dice la reforma laboral?…). Indica las fuentes;
  al pulsar una fuente se abre el detalle del documento **en la propia app**
  (sin salir). Tiene sugerencias rápidas y funciona tanto con la búsqueda local
  (siempre) como, con una clave API gratuita, con respuestas de **IA avanzada
  tipo GPT (Google Gemini o Groq)**.
- **Verificador de actualizaciones**: compara el sitemap real con los datos
  almacenados y detecta contenido nuevo, modificado o retirado. Se activa con
  el botón **«Comprobar ahora»** (solo manual). Cuando hay páginas **nuevas de
  verdad**, el botón **«Descargar novedades»** se habilita; al pulsarlo se bajan
  esas páginas, se regeneran los datos y la app se refresca al instante. El
  panel de resultados se puede **contraer/ocultar** con el botón **«Contraer»**
  de su encabezado, sin recargar la página. Si «Comprobar ahora» dice
  «0 nuevas», significa que tus datos ya están al día.
- Diseño responsivo y profesional (Bootstrap), acorde a la marca FENALCO.

### Asistente de IA tipo GPT (configúralo gratis en 5 minutos)

El asistente **ya funciona sin configuración** con una búsqueda inteligente
sobre los datos. Para que responda con **IA generativa real (tipo GPT)**, solo
necesitas una clave **gratuita**, de cualquiera de estas dos opciones:

#### Opción A → Google Gemini

1. Ve a **https://aistudio.google.com/apikey** e inicia sesión con tu cuenta
   de Google.
2. Pulsa el botón **"Create API key"** y cópiala (empieza por `AIza...`).
3. En el proyecto, copia `.env.example` a `.env`:

   ```bash
   cp .env.example .env        # en Windows:  copy .env.example .env
   ```

4. Abre `.env` y pega tu clave:

   ```
   GEMINI_API_KEY=AIzaTuClaveAqui
   ```

5. Reinicia la app: `python app.py`.

#### Opción B → Groq (alternative gratuita, muy rápida)

1. Ve a **https://console.groq.com/keys** e inicia sesión (se puede con
   Google o GitHub).
2. Pulsa **"Create API Key"**, dale un nombre y cópiala.
3. En `.env` pega tu clave (deja `GEMINI_API_KEY` vacío para que Groq sea el
   proveedor activo):

   ```
   GROQ_API_KEY=gsk_xxxxxxxx
   ```

4. Reinicia la app: `python app.py`.

#### Cómo verificar que quedó activo

Bajo el chat, el indicador cambiará de **"Modo local (sin clave API)"** a
**"IA conectada · Groq · GPT-OSS 20B"** (o el modelo de Gemini/otro que tengas
configurado). Haz una pregunta y en **1–2 segundos** recibirás una respuesta
elaborada con sus fuentes.

> Nota: en este proyecto las claves ya vienen configuradas en el archivo
> `.env` (que no se sube al repositorio).
>
> **Rendimiento:** el asistente usa **Groq** por defecto porque es muy rápido
> (~1–2 s); si Groq fallara, recurre automáticamente a **Google Gemini**.


## Estructura

```
scraphanwen/
├─ run.py                      # punto de entrada para scrapear
├─ export.py                   # punto de entrada para exportar
├─ app.py                      # punto de entrada de la interfaz web
├─ requirements.txt
├─ src/fenalco_scraper/
│  ├─ config.py                # rutas, categorías, parámetros
│  ├─ session.py               # sesión HTTP con reintentos y cortesía
│  ├─ sitemap.py               # descarga y clasificación del sitemap
│  ├─ extractor.py             # HTML -> registro estructurado
│  ├─ crawler.py               # pool de hilos + checkpoint + JSONL
│  └─ export.py                # JSONL -> JSON / CSV / Markdown
├─ src/webapp/                 # interfaz gráfica (Dash + Bootstrap)
│  ├─ data.py                  # carga/filtrado/orden de los registros
│  ├─ layout.py                # componentes visuales (filtros, tabla, métricas)
│  ├─ callbacks.py             # lógica reactiva de la interfaz
│  ├─ detail.py                # panel de detalle de un registro
│  ├─ updates.py               # verificador de actualizaciones (auto y manual)
│  └─ assistant.py             # asistente de IA (búsqueda RAG + Gemini)
├─ data/                       # sitemap.xml y listas de URLs descargadas
└─ output/                     # resultados generados
```

## Notas

- Se recomienda no usar valores de `--workers` muy altos ni `--delay` muy bajo
  para no saturar el servidor de FENALCO.
- Las páginas auxiliares (perfil, shop, helpdesk, slides) redirigen al login y
  no contienen datos públicos, por eso se excluyen por defecto.
- `publish_date` se extrae de las etiquetas `<time>` / metadatos; para los
  posts que no la exponen se usa `lastmod` del sitemap como referencia.