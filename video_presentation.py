#!/usr/bin/env python3
"""Video Presentation - reproduz um vídeo em loop com um texto sobreposto.

Uso:
    python3 video_presentation.py [caminho_do_video]

Tudo é configurado de forma interativa no terminal. A reprodução usa o
ffplay (pacote ffmpeg) com o filtro drawtext, então nada é salvo em disco
além de um arquivo temporário com o texto.
"""

import glob
import os
import readline
import shutil
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".mpg", ".mpeg", ".gif"}

COLORS = {
    "branco": "white",
    "preto": "black",
    "amarelo": "yellow",
    "vermelho": "red",
    "verde": "lime",
    "azul": "dodgerblue",
    "laranja": "orange",
    "rosa": "hotpink",
}

POSITIONS = {
    "centro": ("(w-text_w)/2", "(h-text_h)/2"),
    "topo": ("(w-text_w)/2", "h*0.06"),
    "base": ("(w-text_w)/2", "h-text_h-h*0.06"),
    "esquerda-topo": ("w*0.04", "h*0.06"),
    "direita-topo": ("w-text_w-w*0.04", "h*0.06"),
    "esquerda-base": ("w*0.04", "h-text_h-h*0.06"),
    "direita-base": ("w-text_w-w*0.04", "h-text_h-h*0.06"),
}

TIMER_MODES = {
    "desligado": "Sem timer",
    "regressivo": "Contagem regressiva (ex.: 50, 49, 48 ... 0)",
    "progressivo": "Contagem progressiva (ex.: 0, 1, 2 ... até o limite)",
}

TIMER_PLACES = {
    "lado": "Ao lado do texto",
    "abaixo": "Abaixo do texto",
    "acima": "Acima do texto",
}

BOLD = "\033[1m"
DIM = "\033[2m"
REVERSE = "\033[7m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K\r"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


# ---------------------------------------------------------------- utilidades

def info(msg):
    print(f"{CYAN}{msg}{RESET}")


def error(msg):
    print(f"{RED}✗ {msg}{RESET}")


def ok(msg):
    print(f"{GREEN}✓ {msg}{RESET}")


def ask(prompt, default=None):
    suffix = f" {DIM}[{default}]{RESET}" if default is not None else ""
    try:
        value = input(f"{BOLD}{prompt}{RESET}{suffix}: ").strip()
    except EOFError:
        print()
        sys.exit(0)
    return value if value else (str(default) if default is not None else "")


def ask_int(prompt, default, minimum, maximum):
    while True:
        value = ask(prompt, default)
        try:
            number = int(value)
        except ValueError:
            error("Digite um número inteiro.")
            continue
        if minimum <= number <= maximum:
            return number
        error(f"Digite um valor entre {minimum} e {maximum}.")


def read_key(fd):
    ch = os.read(fd, 1)
    if ch == b"\x1b":
        seq = os.read(fd, 2)
        return {b"[A": "up", b"[B": "down"}.get(seq, "")
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b"\x03":
        raise KeyboardInterrupt
    if ch == b"\x04":
        raise EOFError
    return ch.decode(errors="ignore")


def menu(title, options, default=None):
    """Menu interativo: ↑/↓ (ou j/k) para mover, Enter para escolher.

    `options` é um dict {chave: rótulo}; retorna a chave escolhida.
    """
    keys = list(options)
    index = keys.index(default) if default in options else 0

    if not sys.stdin.isatty():
        print(f"{BOLD}{title}{RESET}")
        for i, key in enumerate(keys, 1):
            print(f"  {i}) {options[key]}")
        while True:
            value = ask("Opção", index + 1)
            if value.isdigit() and 1 <= int(value) <= len(keys):
                return keys[int(value) - 1]
            error("Opção inválida.")

    def render(first):
        if not first:
            sys.stdout.write(f"\033[{len(keys)}A")
        for i, key in enumerate(keys):
            label = f"{i + 1}) {options[key]}"
            if i == index:
                line = f"  {CYAN}❯ {REVERSE} {label} {RESET}"
            else:
                line = f"    {label}"
            sys.stdout.write(f"{CLEAR_LINE}{line}\n")
        sys.stdout.flush()

    print(f"{BOLD}{title}{RESET} {DIM}(↑/↓ e Enter){RESET}")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sys.stdout.write(HIDE_CURSOR)
    render(True)
    try:
        tty.setcbreak(fd)
        while True:
            key = read_key(fd)
            if key in ("up", "k"):
                index = (index - 1) % len(keys)
            elif key in ("down", "j"):
                index = (index + 1) % len(keys)
            elif key.isdigit() and 1 <= int(key) <= len(keys):
                index = int(key) - 1
                render(False)
                break
            elif key == "enter":
                break
            else:
                continue
            render(False)
    except EOFError:
        print()
        sys.exit(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(SHOW_CURSOR)

    # Recolhe o menu numa linha só com a opção escolhida
    sys.stdout.write(f"\033[{len(keys) + 1}A")
    for _ in range(len(keys) + 1):
        sys.stdout.write(f"{CLEAR_LINE}\n")
    sys.stdout.write(f"\033[{len(keys) + 1}A")
    print(f"{BOLD}{title}{RESET} {GREEN}{options[keys[index]]}{RESET}")
    return keys[index]


def ask_yes_no(prompt, default=False):
    choice = menu(prompt, {"s": "Sim", "n": "Não"}, "s" if default else "n")
    return choice == "s"


def path_completer(text, state):
    """Autocompletar caminhos com TAB."""
    expanded = os.path.expanduser(text)
    matches = []
    for match in glob.glob(expanded + "*"):
        if os.path.isdir(match):
            match += "/"
        if text.startswith("~"):
            match = "~" + match[len(os.path.expanduser("~")):]
        matches.append(match)
    return matches[state] if state < len(matches) else None


def escape_filter_value(value):
    """Escapa um valor para ser usado entre aspas simples no filtergraph."""
    return value.replace("\\", "\\\\").replace("'", "'\\\\\\''").replace(":", "\\:")


def find_font():
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "sans-serif:bold"],
            capture_output=True, text=True, check=True,
        )
        if result.stdout and os.path.isfile(result.stdout):
            return result.stdout
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


def format_timer(seconds):
    """Abaixo de 60 mostra só os segundos; acima disso, M:SS (ou H:MM:SS)."""
    if seconds < 60:
        return str(seconds)
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}:{secs:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


# ---------------------------------------------------------------- perguntas

def ask_video(initial=None):
    readline.set_completer_delims(" \t\n")
    readline.set_completer(path_completer)
    readline.parse_and_bind("tab: complete")
    candidate = initial
    try:
        while True:
            if candidate is None:
                candidate = ask("Caminho do vídeo (TAB autocompleta)")
            path = os.path.abspath(os.path.expanduser(candidate.strip().strip("'\"")))
            candidate = None
            if not os.path.isfile(path):
                error("Arquivo não encontrado.")
                continue
            if os.path.splitext(path)[1].lower() not in VIDEO_EXTS:
                if not ask_yes_no("A extensão não parece ser de vídeo. Usar mesmo assim?"):
                    continue
            ok(f"Vídeo: {path}")
            return path
    finally:
        readline.set_completer(None)


def ask_text():
    info("Digite o texto que ficará sobre o vídeo.")
    info("Pode usar várias linhas; deixe uma linha vazia para terminar.")
    lines = []
    while True:
        try:
            line = input(f"{DIM}> {RESET}")
        except EOFError:
            print()
            break
        if not line and lines:
            break
        if line or lines:
            lines.append(line)
    return "\n".join(lines)


def ask_window(settings):
    info("\nTamanho da janela (você ainda pode redimensioná-la com o mouse).")
    settings["width"] = ask_int("Largura em pixels", settings["width"], 100, 7680)
    settings["height"] = ask_int("Altura em pixels", settings["height"], 100, 4320)


def ask_style(settings):
    info("\nEstilo do texto")
    settings["font_size"] = ask_int(
        "Tamanho da fonte (% da altura do vídeo)", settings["font_size"], 1, 50
    )
    settings["color"] = menu("Cor do texto:", {c: c for c in COLORS}, settings["color"])
    settings["position"] = menu("Posição do texto:", {p: p for p in POSITIONS}, settings["position"])
    settings["box"] = ask_yes_no("Fundo escuro atrás do texto?", settings["box"])
    if has_audio(settings["video"]):
        settings["mute"] = not ask_yes_no("Reproduzir COM som?", not settings["mute"])
    else:
        error("Este vídeo não tem faixa de áudio, então vai tocar sem som.")


def ask_timer(settings):
    info("\nTimer")
    settings["timer_mode"] = menu("Tipo de timer:", TIMER_MODES, settings["timer_mode"])
    if settings["timer_mode"] == "desligado":
        return
    info("Abaixo de 60 segundos mostra só os segundos; acima disso mostra em minutos (M:SS).")
    settings["timer_seconds"] = ask_int(
        "Duração em segundos", settings["timer_seconds"], 1, 24 * 3600
    )
    settings["timer_place"] = menu("Onde mostrar o timer:", TIMER_PLACES, settings["timer_place"])


# ---------------------------------------------------------------- reprodução

def has_audio(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return True


def video_height(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
        )
        return int(result.stdout.strip().splitlines()[0])
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        return 720


def compose_text(settings, elapsed):
    """Texto final exibido, já com o timer (se houver)."""
    text = settings["text"]
    if settings["timer_mode"] == "desligado":
        return text
    limit = settings["timer_seconds"]
    if settings["timer_mode"] == "regressivo":
        value = max(limit - elapsed, 0)
    else:
        value = min(elapsed, limit)
    timer = format_timer(value)
    if not text:
        return timer
    place = settings["timer_place"]
    if place == "abaixo":
        return f"{text}\n{timer}"
    if place == "acima":
        return f"{timer}\n{text}"
    lines = text.split("\n")
    lines[-1] = f"{lines[-1]}   {timer}"
    return "\n".join(lines)


def write_text_file(path, content):
    # Escrita atômica: o ffplay relê o arquivo a cada quadro e nunca pode
    # encontrá-lo pela metade.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def timer_loop(settings, path, stop):
    start = time.monotonic()
    last = None
    while not stop.is_set():
        content = compose_text(settings, int(time.monotonic() - start))
        if content != last:
            write_text_file(path, content)
            last = content
        stop.wait(0.1)


def build_filter(settings, text_file, font):
    x, y = POSITIONS[settings["position"]]
    color = COLORS[settings["color"]]
    outline = "white" if color == "black" else "black"
    size = max(8, round(video_height(settings["video"]) * settings["font_size"] / 100))
    parts = [
        f"textfile='{escape_filter_value(text_file)}'",
        "expansion=none",
        "text_align=C",
        f"fontsize={size}",
        f"fontcolor={color}",
        f"borderw={max(1, round(size * 0.06))}",
        f"bordercolor={outline}@0.8",
        f"line_spacing={round(size * 0.2)}",
        f"x={x}",
        f"y={y}",
    ]
    if font:
        parts.insert(1, f"fontfile='{escape_filter_value(font)}'")
    if settings["box"]:
        parts += ["box=1", "boxcolor=black@0.5", f"boxborderw={round(size * 0.4)}"]
    if settings["timer_mode"] != "desligado":
        parts.append("reload=1")
    return "drawtext=" + ":".join(parts)


def play(settings, font):
    fd, text_file = tempfile.mkstemp(suffix=".txt", prefix="video_presentation_")
    os.close(fd)
    write_text_file(text_file, compose_text(settings, 0))
    cmd = [
        "ffplay", "-hide_banner", "-loglevel", "error",
        "-loop", "0",
        "-x", str(settings["width"]), "-y", str(settings["height"]),
        "-window_title", "Video Presentation",
        "-vf", build_filter(settings, text_file, font),
    ]
    if settings["mute"]:
        cmd.append("-an")
    cmd.append(settings["video"])

    sound = "desligado" if settings["mute"] or not has_audio(settings["video"]) else "ligado"
    info(f"\nReproduzindo em loop (som {sound}). Atalhos na janela:")
    print("  q / ESC  fechar    f  tela cheia    espaço  pausar    ← →  voltar/avançar")

    stop = threading.Event()
    timer = None
    if settings["timer_mode"] != "desligado":
        timer = threading.Thread(target=timer_loop, args=(settings, text_file, stop), daemon=True)
        timer.start()
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if timer:
            timer.join()
        os.unlink(text_file)


# ---------------------------------------------------------------- main

MAIN_MENU = {
    "play": "Reproduzir de novo",
    "text": "Mudar o texto",
    "timer": "Configurar timer",
    "window": "Mudar tamanho da janela",
    "style": "Mudar estilo do texto / som",
    "video": "Escolher outro vídeo",
    "quit": "Sair",
}


def main():
    if not shutil.which("ffplay"):
        error("ffplay não encontrado. Instale o ffmpeg (ex.: sudo pacman -S ffmpeg).")
        sys.exit(1)
    font = find_font()

    print(f"\n{BOLD}=== Video Presentation ==={RESET}\n")
    settings = {
        "video": ask_video(sys.argv[1] if len(sys.argv) > 1 else None),
        "width": 1280,
        "height": 720,
        "font_size": 8,
        "color": "branco",
        "position": "centro",
        "box": False,
        "mute": False,
        "timer_mode": "desligado",
        "timer_seconds": 60,
        "timer_place": "lado",
    }
    print()
    settings["text"] = ask_text()
    ask_timer(settings)
    ask_window(settings)
    ask_style(settings)

    while True:
        play(settings, font)
        print()
        choice = menu("O que deseja fazer?", MAIN_MENU, "play")
        if choice == "quit":
            break
        if choice == "text":
            settings["text"] = ask_text()
        elif choice == "timer":
            ask_timer(settings)
        elif choice == "window":
            ask_window(settings)
        elif choice == "style":
            ask_style(settings)
        elif choice == "video":
            settings["video"] = ask_video()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write(SHOW_CURSOR)
        print()
