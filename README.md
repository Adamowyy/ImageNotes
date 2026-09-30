# ImageNotes

Notowanie na zdjęciach i mapach o dużej rozdzielczości. Windows, Python i Qt.

## Uruchamianie

Ze skrótu na pulpicie albo przez przeciągnięcie zdjęcia na ten skrót lub do wnętrza otwartego okna.
Działa jedna instancja, więc kolejne zdjęcie wczyta się w tym samym oknie.
Ze źródeł: `pythonw ImageNotes.pyw`.

## Obsługa

Prawy przycisk przesuwa po zdjęciu, kółko przybliża pod kursorem, `Ctrl+0` dopasowuje, `F11` to pełny
ekran. Narzędzia: `V` zaznaczanie, `T` tekst, `A` strzałka, `X` krzyżyk, `C` checkmark, `B` rysowanie.
`Del` usuwa, `Ctrl+Z` cofa, `Ctrl+S` wymusza zapis. Kolor, grubość, rozmiar i kąt ustawia panel
w prawym górnym rogu, ostatnie zdjęcia siedzą pod bąbelkiem w lewym.

## Zapis

Oryginał jest tylko czytany. Kopia robocza powstaje przy pierwszej edycji i jest nadpisywana około
2 sekundy po ostatniej zmianie, razem z plikiem JSON z listą notatek. Dzięki temu po ponownym
otwarciu edytujesz notatki, a nie wypalony obraz. Format wybiera `SAVE_FORMAT` w
`imagenotes/config.py`: PNG daje ostrzejsze napisy, JPEG zapisuje się szybciej i waży dużo mniej.

## Pliki

```
imagenotes/   okno, płótno, notatki, zapis, panel narzędzi
tools/        ikona, skrót, build EXE, publikacja wydania
tests/        selftest.py, visual_check.py
```

## Bez Pythona

`python tools/build_exe.py` (albo `--onedir`) tworzy plik do wysłania komuś, kto nie ma Pythona.
To samo leży w zakładce Releases razem z instrukcją. EXE trzyma dane obok siebie, a gdy nie ma tam
prawa zapisu, w `%LOCALAPPDATA%\ImageNotes`.

## Testy

```bash
PY=/sciezka/do/python.exe
QT_QPA_PLATFORM=offscreen "$PY" tests/selftest.py
"$PY" tests/visual_check.py
```

Wygląd sprawdzaj w prawdziwym oknie, bo backend `offscreen` nie ma czcionek.

## Pułapki Qt

Qt 6 nie wczyta obrazu zajmującego ponad 256 MB pamięci, dlatego `config.py` podnosi limit
(`QIMAGE_ALLOC_LIMIT_MB`). Objaw bywa mylący: plik zapisuje się poprawnie, ale nie chce się otworzyć.
`QFontMetricsF.boundingRect()` dla pojedynczej linii zwraca prostokąt przesunięty o (100000, 100000),
więc obrys tekstu liczę z `QPainterPath`, którym go rysuję. `pythonw.exe` ze środowiska uv to
trampolina wskrzeszająca konsolowy `python.exe` i mruga czarnym oknem, więc skrót wskazuje na
interpreter bazowy.

## Płynność

Obraz trzymany jest jako piramida mipmap: przy rysowaniu wybierany jest poziom o skali zbliżonej do
aktualnej i tylko widoczny fragment. Koszt klatki zależy więc od rozmiaru okna, nie zdjęcia, i na
mapie 10 000 x 8 000 px wynosi 2,4 ms przy powiększeniu 100% oraz 4 ms przy dopasowaniu.

Autor: Adam Warzecha, wszelkie prawa zastrzeżone (patrz `LICENSE`).
