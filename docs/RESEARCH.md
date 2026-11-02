# S.A.M.U.E.L. v5 — Research notes

Research done before building the v5 HUD (Nov 2026). Every library, API, model and
voice name used in the code was checked against the source linked here. Where
something could not be verified it is configurable instead of hard-coded.

## 1. What the MCU JARVIS / FRIDAY interfaces look like

| Finding | Source |
| --- | --- |
| The Iron Man screen UIs were made by several studios: Perception (Iron Man 2 glass phone, coffee table, Stark Expo screens), Cantina Creative (in-helmet HUDs for Iron Man 2/3, Avengers, Age of Ultron, Civil War) and Territory Studio (Age of Ultron lab screens). | [Engadget on Perception](https://www.engadget.com/2015-12-14-perception-ui-design.html), [Creative Bloq on Cantina](https://www.creativebloq.com/3d/cinema-4d-secrets-iron-mans-interface-61515419), [VICE on Territory](https://www.vice.com/en/article/take-an-exclusive-look-inside-iron-mans-suit-from-marvels-avengers-age-of-ultron/) |
| HUD designer Jayse Hansen: concentric rings and "exploded pie pieces" recur throughout; palette is heavy black and grey with muted reds, oranges and blues; he worked with an A-10 pilot so the UI "never strays too far outside the possible". | [The Verge interview](https://www.theverge.com/2012/5/28/3047634/iron-man-hud-avengers-jayse-hansen-artwork) |
| Territory grounded the Stark lab screens in avionics, robotics, clinical and military HUDs; screens show *constant activity* so JARVIS feels "always there, working behind the scenes". | [VICE](https://www.vice.com/en/article/take-an-exclusive-look-inside-iron-mans-suit-from-marvels-avengers-age-of-ultron/) |
| Civil War (FRIDAY era) HUD moved to a darker, more grounded, "militaristic" language; light sources come from the rim of the lens. | [AWN on Cantina / Civil War](https://www.awn.com/vfxworld/cantina-creative-goes-huds-captain-america-civil-war) |
| Perception's philosophy: motion should support the performance, not obscure it. | [Pushing Pixels interview with John LePore](https://www.pushing-pixels.org/2016/07/20/the-craft-of-screen-graphics-and-movie-user-interfaces-interview-with-john-lepore.html) |

**Design decisions taken from this**

- Near-black navy background, one dominant hue per persona, a single warm accent for warnings. No rainbow of status colours (v4 used eight).
- Concentric, counter-rotating rings, fine tick marks with degree labels, segmented arcs, a radar sweep and a radial voice-waveform ring around an arc-reactor core.
- Chamfered (cut-corner) panels with bright corner accents, small index numbers ("01 //"), thin rules and tiny tick marks: avionics-style framing.
- Constant but quiet activity (slow rotations, blinking live LEDs, sparklines) so the HUD feels alive while idle, and stronger motion only when listening, thinking or speaking.
- Legibility first: condensed sans (Rajdhani) for labels, monospace (JetBrains Mono) for numbers, a geometric display face (Orbitron) only for the wordmark and the clock.
- JARVIS = cyan/ice blue. FRIDAY = warm amber with a cyan accent, which is my reading of the warmer, darker Civil War-era HUDs. It is an interpretation, not an official palette.

## 2. JARVIS vs FRIDAY as characters

| Finding | Source |
| --- | --- |
| F.R.I.D.A.Y. = "Female Replacement Intelligent Digital Assistant Youth", Tony's AI after J.A.R.V.I.S. became Vision in *Age of Ultron*; voiced by Kerry Condon with her Irish accent, in contrast to JARVIS's male English voice. | [Wikipedia: F.R.I.D.A.Y.](https://en.wikipedia.org/wiki/F.R.I.D.A.Y.), [Collider](https://collider.com/who-was-kerry-condon-in-the-mcu/), [Irish Examiner](https://www.irishexaminer.com/business/technology/arid-20325713.html) |

Implemented as two personas (`samuel/personas.py`): name, expansion, palette,
honorific ("sir" vs "boss", both configurable), greeting and acknowledgement
lines, and a separate Piper voice setting.

## 3. Voice (offline)

| Item | Verified | Source |
| --- | --- | --- |
| Piper TTS. `rhasspy/piper` is archived ("Development has moved") to `OHF-Voice/piper1-gpl` (`pip install piper-tts`). The last standalone binary release of the old project is `2023.11.14-2` (`piper_linux_x86_64.tar.gz`), which is what v4 uses. | yes | [rhasspy/piper](https://github.com/rhasspy/piper), [piper1-gpl](https://github.com/OHF-Voice/piper1-gpl), [CLI docs](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md) |
| JARVIS voice `en_GB-alan-medium` (v4 default) exists. | yes | [voices.json](https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json) |
| FRIDAY voice: there is **no Irish-English (`en_IE`) Piper voice** in the official list. Female British voices that do exist: `en_GB-jenny_dioco-medium`, `en_GB-cori-medium`, `en_GB-cori-high`, `en_GB-alba-medium`, `en_GB-southern_english_female-low`. Default for FRIDAY is `en_GB-jenny_dioco-medium`; configurable. | yes | [voices.json](https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json) |
| Each Piper voice ships an `.onnx.json` with `audio.sample_rate`; v5 reads it instead of assuming 22050 Hz. | yes | same |
| Vosk small English models that exist: `vosk-model-small-en-in-0.4` (v4 default), `vosk-model-small-en-us-0.15`, `vosk-model-small-en-us-zamia-0.5`. | yes | [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models) |
| Python 3.13 removed the `audioop` module that v4 used for 44.1 kHz→16 kHz resampling, so v5 has a small pure-Python resampler. | yes | [PEP 594](https://peps.python.org/pep-0594/) |

## 4. Free, key-less data sources

| API | Notes | Source |
| --- | --- | --- |
| Wikipedia REST summary `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` | Returns `title`, `description`, `extract`, `content_urls`. Tested live. A descriptive `User-Agent` is sent as Wikimedia asks. | [example response](https://en.wikipedia.org/api/rest_v1/page/summary/Photosynthesis) |
| Wikipedia OpenSearch `w/api.php?action=opensearch` | Resolves spoken topics ("black holes") to article titles. | [MediaWiki API](https://www.mediawiki.org/wiki/API:Opensearch) |
| Open-Meteo forecast `api.open-meteo.com/v1/forecast?current=...` | No key for non-commercial use. Current temperature, apparent temperature, humidity, wind, `weather_code` (WMO codes mapped to text in the docs). Tested live. | [Open-Meteo docs](https://open-meteo.com/en/docs), [terms](https://open-meteo.com/en/terms) |
| Open-Meteo geocoding `geocoding-api.open-meteo.com/v1/search?name=` | Turns a configured city name into coordinates. | [Geocoding docs](https://open-meteo.com/en/docs/geocoding-api) |

Weather is **off until a city or coordinates are set in the config**. I don't
know where Samuel is and didn't guess.

## 5. Learning science

| Item | Source |
| --- | --- |
| SuperMemo SM-2: EF starts at 2.5; intervals I(1)=1, I(2)=6, I(n)=I(n-1)·EF; quality 0–5; EF' = EF + (0.1 − (5−q)(0.08 + (5−q)·0.02)), floor 1.3; q < 3 restarts repetitions. The original Pascal source updates EF on every grade, which v5 follows. | [SM-2 description](https://www.super-memory.com/english/ol/sm2.htm), [SM-2 source code](https://super-memory.org/archive/english/ol/sm2source.htm) |

Used for flashcards (`samuel/learning/srs.py`), stored in SQLite (Python stdlib
`sqlite3`, no new dependency). Flashcards and quizzes are generated from the
lesson text itself (cloze deletions), so they work without any LLM.

## 6. Optional LLM backends (off by default)

| Backend | Verified API | Source |
| --- | --- | --- |
| Ollama (local) | `POST /api/chat` with `model`, `messages`, `stream:false`; reply in `message.content`. | [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md) |
| Models small enough to try on 4 GB RAM (download sizes from ollama.com) | `qwen2.5:0.5b` (398 MB), `gemma3:1b` (806 MB), `llama3.2:1b` (1.3 GB). On a 4 GB machine only the 0.5b–1b class is realistic, and it is slow on a 2010 CPU. | [ollama.com/library](https://ollama.com/library) |
| Any OpenAI-compatible cloud endpoint | `POST {base_url}/chat/completions`. Key is read from an environment variable (default `SAMUEL_LLM_API_KEY`), never stored in code or config. | — |

## 7. Linux system control (all optional, detected at runtime)

| Feature | Tool tried, in order |
| --- | --- |
| Volume | `pactl` (PulseAudio/PipeWire), then `amixer` |
| Brightness | `brightnessctl`, then `xbacklight` |
| Lock screen | `loginctl lock-session`, then `xdg-screensaver lock` |
| Screenshot | Qt `QScreen.grabWindow(0)` (no pyautogui needed), then `gnome-screenshot`/`scrot`/`grim` |
| Open apps | Small allow-list of friendly names mapped to common executables (`shutil.which`) — voice can never run arbitrary shell commands |
| Notifications | `notify-send` if present |

## 8. Fonts (bundled, licence verified)

| Font | Licence | Source |
| --- | --- | --- |
| Rajdhani (Indian Type Foundry) | SIL OFL 1.1 | [google/fonts/ofl/rajdhani](https://github.com/google/fonts/tree/main/ofl/rajdhani) |
| Orbitron (The League of Moveable Type), reserved font name "Orbitron", shipped unmodified | SIL OFL 1.1 | [google/fonts/ofl/orbitron](https://github.com/google/fonts/tree/main/ofl/orbitron) |
| JetBrains Mono | SIL OFL 1.1 | [google/fonts/ofl/jetbrainsmono](https://github.com/google/fonts/tree/main/ofl/jetbrainsmono) |

Licence texts are in `samuel/ui/fonts/`.

## 9. Performance budget for a Dell Latitude E5410 (2010, 4 GB RAM)

- No QtWebEngine, no OpenGL, no blur effects: everything is `QPainter` on the raster engine.
- One shared animation clock (30 fps while active, lower when idle, stopped when minimised) instead of a timer per widget.
- Static layers (background grid, vignette, tick ring with degree labels) are rendered once into pixmaps and re-used.
- Glow is faked with 2–3 stacked strokes of decreasing alpha rather than real blur.
- Two extra savings added after profiling: the fixed outer ring is baked into the static
  pixmap after boot, and the reactor coils are drawn once and only rotated afterwards
  (reactor frame went from ~6.7 ms to ~4.8 ms in software rendering on the build machine).
- Three frame rates: 30 fps while listening/thinking/speaking, 15 fps idle, 8 fps
  "standby" after 45 s without activity. `--lite` (or `"lite": true`) drops the radar
  sweep and bloom strokes and uses 20/10/5 fps.

**Measured** (offscreen Qt, 1600×900, `tools/capture_screens.py`, 8-core Xeon VM. Not measured on
the E5410 itself; a 2010 laptop CPU will need a larger share): about 100–110 MB RSS for the whole app,
~12 % of one core idle at 15 fps, ~7.5 % in standby. At 1366×768: ~9 % idle, ~6 % standby,
~5.6 % idle in `--lite`.

