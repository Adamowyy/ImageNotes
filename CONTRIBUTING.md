# Contributing

A small, focused tool: one Python package and no dependencies beyond PySide6.

## Running from source

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe ImageNotes.pyw      # or: -m imagenotes
```

## Tests

Both suites run headless:

```bash
QT_QPA_PLATFORM=offscreen python tests/selftest.py --no-big   # fast
QT_QPA_PLATFORM=offscreen python tests/selftest.py            # + 12000x8000 perf test
python tests/visual_check.py                                  # real window, real fonts
```

`selftest.py` covers the annotation model, hit testing, panning and zooming,
autosave and the save queue. The `offscreen` backend has no font database on
Windows, so text renders as empty boxes there. For anything that depends on how
text looks, use `tests/visual_check.py`, which opens a real window and writes
screenshots to `tests/artifacts/`.

Neither suite touches the real `workspace/`; both redirect the `config` paths
into a temporary directory.

## Building the exe

```bash
python tools/build_exe.py            # single file + portable ZIP
python tools/build_exe.py --onedir   # folder with the exe, faster start
```

That produces `dist/ImageNotes.exe` and a ZIP to hand to someone who has no
Python.

## Style

- Comments and docstrings in English, short, and about *why*, not *what* the
  next line does.
- User-facing strings (labels, dialogs, tooltips) are Polish; there is no
  translation layer yet.
- No new dependencies: the app ships as a single file on purpose.

## Reporting a bug

Say what you did, what you expected and what happened, and mention the image you
used. Its size matters: the large-image path is the interesting one.
