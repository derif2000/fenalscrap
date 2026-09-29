"""Configuración de Gunicorn - leída automáticamente al iniciar (sin --config).

Gunicorn busca 'gunicorn.conf.py' en el directorio de trabajo (raíz del proyecto)
automáticamente, sin necesidad de pasarlo como argumento. Esto garantiza que
timeout, worker_class y threads se apliquen SIEMPRE, incluso cuando Render lanza
gunicorn con su comando auto-detectado mínimo ('gunicorn app:server --bind ...').
"""
import os

# Binding: Render inyecta $PORT; fallback para desarrollo local
bind = f"0.0.0.0:{os.environ.get('PORT', '8050')}"

# Workers y modelo de concurrencia
# - 1 proceso: el singleton FenalcoData se comparte sin duplicar RAM
# - gthread: permite atender peticiones cortas (CSS, layout) mientras Gemini trabaja
workers = 1
worker_class = "gthread"
threads = 4

# Timeouts
# - 300s (5 min): cubre descarga de PDF + OCR + Gemini con margen amplio
# - El deadline interno del asistente (240s) garantiza que nunca se llegue aqui
timeout = 300
graceful_timeout = 30
keepalive = 5

# Reciclaje de workers para liberar memoria acumulada (leaks de pypdf / PIL)
max_requests = 300
max_requests_jitter = 30

# Logging visible en Render
accesslog = "-"
errorlog = "-"
loglevel = "info"
