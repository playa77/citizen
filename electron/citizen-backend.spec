# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for citizen-desktop backend.
Bundles the FastAPI/Uvicorn app into a standalone binary.

Produces a --onedir layout:
  dist/citizen-backend/
    citizen-backend          # executable
    _internal/               # all dependencies

Usage:
    cd /home/daniel/projects/citizen-desktop
    pyinstaller electron/citizen-backend.spec

Version: 1.0.0 | 2026-07-10
"""

import sys
from pathlib import Path

# Assumes pyinstaller is run from the project root directory
PROJECT_ROOT = Path.cwd().resolve()

sys.setrecursionlimit(10000)

a = Analysis(
    [str(PROJECT_ROOT / 'app/main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Include the static frontend files (served by FastAPI)
        (str(PROJECT_ROOT / 'static'), 'static'),
        # Include Alembic migrations (for auto-migration on startup)
        (str(PROJECT_ROOT / 'alembic'), 'alembic'),
        (str(PROJECT_ROOT / 'alembic.ini'), '.'),
    ],
    hiddenimports=[
        # Uvicorn internals (dynamically imported, missed by PyInstaller)
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # FastAPI multipart support (file uploads)
        'multipart',
        # App modules (dynamically imported routes/services)
        'app.api.routes',
        'app.api.routes.analyze',
        'app.api.routes.cases',
        'app.api.routes.conversations',
        'app.api.routes.corpus',
        'app.api.routes.ingest',
        'app.api.routes.intake',
        'app.api.routes.meta',
        'app.api.routes.presets',
        'app.services',
        'app.services.reasoning',
        'app.services.chat_reasoning',
        'app.services.retrieval',
        'app.services.corpus',
        'app.services.ocr',
        'app.services.calculation',
        'app.services.cache',
        'app.services.corpus_readiness',
        'app.services.parameter_store',
        'app.services.rules_engine',
        'app.services.case_chat',
        'app.services.audit',
        'app.services.presets',
        'app.services.verification',
        'app.services.intake',
        'app.services.conversation',
        'app.services.prompts',
        'app.utils',
        'app.utils.text',
        'app.utils.tokens',
        'app.utils.pdf',
        'app.utils.image',
        'app.core',
        'app.core.config',
        'app.core.pipeline',
        'app.core.router',
        'app.middleware',
        'app.middleware.disclaimer',
        'app.middleware.rate_limit',
        'app.db',
        'app.db.models',
        'app.db.session',
        'app.db.vector_backend',
        # SQLAlchemy dialects (must be explicit for frozen apps)
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.aiosqlite',
        # alembic (for auto-migration)
        'alembic',
        'alembic.config',
        'alembic.command',
        'alembic.runtime',
        'alembic.runtime.environment',
        # sqlite-vec (vector search extension)
        'sqlite_vec',
        # OCR libraries
        'pymupdf',
        'pdfplumber',
        'PIL',
        'PIL.Image',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test suites
        'pytest',
        'pytest_asyncio',
        'tests',
        # Exclude heavy/unused packages
        'tkinter',
        'matplotlib',
        'numpy.core._dotblas',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='citizen-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='citizen-backend',
)
