import ctypes
import datetime
import os
import queue
import shutil
import json
import subprocess
import threading
import webbrowser
import tkinter as tk

import keyring
from openai import OpenAI

import customtkinter as ctk
import pyttsx3
import speech_recognition as sr


APP_NAME = "Robot Tea"
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class RobotTeaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Robot Tea — голосовой помощник")
        self.geometry("900x620")
        self.minsize(760, 540)
        self.configure(fg_color="#0b1020")
        self.events = queue.Queue()
        self.listening = False
        self.engine_lock = threading.Lock()
        self.ai_history = []
        self.ai_busy = False
        self.keep_awake = False
        self.mouse_nudge_active = False
        self.mouse_nudge_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="#111a30", corner_radius=18)
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.orb = ctk.CTkLabel(
            header, text="◉", font=ctk.CTkFont(size=52, weight="bold"),
            text_color="#63d7ff", width=100
        )
        self.orb.grid(row=0, column=0, rowspan=2, padx=(18, 8), pady=14)
        ctk.CTkLabel(
            header, text="ROBOT TEA",
            font=ctk.CTkFont(size=28, weight="bold"), text_color="#f2f7ff"
        ).grid(row=0, column=1, sticky="sw", padx=8, pady=(18, 0))
        ctk.CTkLabel(
            header, text="Голосовой помощник для Windows",
            font=ctk.CTkFont(size=14), text_color="#9eacc8"
        ).grid(row=1, column=1, sticky="nw", padx=8, pady=(0, 18))

        control = ctk.CTkFrame(self, fg_color="transparent")
        control.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        control.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(
            control, text="Система готова. Нажми «Слушать» и произнеси команду.",
            text_color="#b8c8e8", anchor="w", wraplength=560
        )
        self.status.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.listen_button = ctk.CTkButton(
            control, text="🎙 Слушать", width=150, height=42,
            command=self.toggle_listening, corner_radius=12
        )
        self.listen_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.ai_button = ctk.CTkButton(
            control, text="⚙ Настроить ИИ", width=145, height=42,
            command=self.configure_ai, corner_radius=12, fg_color="#263654"
        )
        self.ai_button.grid(row=0, column=2, sticky="e")

        body = ctk.CTkFrame(self, fg_color="#111a30", corner_radius=18)
        body.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            body, text="Журнал помощника",
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="ew")
        self.log = ctk.CTkTextbox(
            body, corner_radius=12, fg_color="#0b1020",
            text_color="#dce8ff", font=ctk.CTkFont(size=13), wrap="word"
        )
        self.log.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.log.configure(state="disabled")

        chatbar = ctk.CTkFrame(self, fg_color="transparent")
        chatbar.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        chatbar.grid_columnconfigure(0, weight=1)
        self.message_entry = ctk.CTkEntry(
            chatbar, placeholder_text="Напиши вопрос ИИ…",
            height=40, corner_radius=12
        )
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.message_entry.bind("<Return>", lambda event: self.send_text_message())
        ctk.CTkButton(
            chatbar, text="Отправить", width=110, height=40,
            command=self.send_text_message, corner_radius=12
        ).grid(row=0, column=1, sticky="e")

        automation = ctk.CTkFrame(self, fg_color="transparent")
        automation.grid(row=4, column=0, padx=20, pady=(0, 8), sticky="ew")
        automation.grid_columnconfigure((0, 1), weight=1)
        self.awake_button = ctk.CTkButton(
            automation, text="🌙 Не засыпать: выкл.", height=38,
            command=self.toggle_keep_awake, corner_radius=10, fg_color="#263654"
        )
        self.awake_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.mouse_button = ctk.CTkButton(
            automation, text="🖱 Двигать мышью: выкл.", height=38,
            command=self.toggle_mouse_nudge, corner_radius=10, fg_color="#263654"
        )
        self.mouse_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        ctk.CTkLabel(
            self,
            text="Голосовые команды: «не засыпай», «двигай мышкой каждую минуту», «останови автоматизацию».",
            text_color="#8292b3", wraplength=820
        ).grid(row=5, column=0, padx=20, pady=(0, 12), sticky="ew")

        self.write_log("Robot Tea запущен. Голосовое распознавание использует интернет.")
        self.write_log("Для диалога с ИИ нажми «Настроить ИИ» и добавь свой API-ключ.")
        self.after(100, self.process_events)

    def toggle_keep_awake(self):
        if self.keep_awake:
            self.disable_keep_awake()
        else:
            self.enable_keep_awake()

    def enable_keep_awake(self):
        if threading.current_thread() is not threading.main_thread():
            self.events.put(("automation_call", "enable_keep_awake"))
            return
        if os.name != "nt":
            self.respond("Защита от сна доступна только в Windows.")
            return
        try:
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            result = ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            if result == 0:
                raise OSError("Windows не приняла запрос предотвращения сна")
            self.keep_awake = True
            self.events.put(("awake_button", True))
            self.respond("Автоматический сон и выключение экрана временно запрещены, пока режим включён.")
        except Exception as exc:
            self.events.put(("log", f"Не удалось включить защиту от сна: {exc}"))
            self.respond("Не удалось включить защиту от сна Windows.")

    def disable_keep_awake(self):
        if threading.current_thread() is not threading.main_thread():
            self.events.put(("automation_call", "disable_keep_awake"))
            return
        try:
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception as exc:
            self.events.put(("log", f"Не удалось снять защиту от сна: {exc}"))
        self.keep_awake = False
        self.events.put(("awake_button", False))
        self.events.put(("status", "Автоматическая политика сна Windows восстановлена."))

    def toggle_mouse_nudge(self):
        if self.mouse_nudge_active:
            self.disable_mouse_nudge()
        else:
            self.enable_mouse_nudge()

    def enable_mouse_nudge(self):
        if os.name != "nt":
            self.respond("Периодическое движение мыши доступно только в Windows.")
            return
        if self.mouse_nudge_active:
            self.respond("Периодическое движение мыши уже включено.")
            return
        self.mouse_nudge_active = True
        self.events.put(("mouse_button", True))
        self.events.put(("log", "Движение мыши включено: небольшое смещение раз в 60 секунд. Это не гарантирует, что игра сочтёт персонажа активным."))
        self.events.put(("status", "Мышь будет немного смещаться раз в минуту."))
        self.events.put(("start_mouse_timer", None))

    def _mouse_nudge_tick(self):
        self.mouse_nudge_job = None
        if not self.mouse_nudge_active:
            return
        try:
            user32 = ctypes.windll.user32
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            point = POINT()
            if user32.GetCursorPos(ctypes.byref(point)):
                screen_w = user32.GetSystemMetrics(0)
                screen_h = user32.GetSystemMetrics(1)
                new_x = point.x + 2 if point.x + 2 < screen_w else max(0, point.x - 2)
                user32.SetCursorPos(new_x, point.y)
                self.after(150, lambda x=point.x, y=point.y: user32.SetCursorPos(x, y) if self.mouse_nudge_active else None)
        except Exception as exc:
            self.events.put(("log", f"Ошибка движения мыши: {exc}"))
        if self.mouse_nudge_active:
            self.mouse_nudge_job = self.after(60000, self._mouse_nudge_tick)

    def disable_mouse_nudge(self):
        self.mouse_nudge_active = False
        self.events.put(("stop_mouse_timer", None))
        self.events.put(("mouse_button", False))
        self.events.put(("status", "Периодическое движение мыши остановлено."))

    def stop_automation(self):
        self.disable_mouse_nudge()
        self.disable_keep_awake()

    def on_close(self):
        self.listening = False
        self.stop_automation()
        self.destroy()

    def write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, message):
        self.status.configure(text=message)

    def toggle_listening(self):
        if self.listening:
            self.listening = False
            self.listen_button.configure(text="🎙 Слушать")
            self.set_status("Прослушивание остановлено.")
            return
        self.listening = True
        self.listen_button.configure(text="■ Остановить")
        self.set_status("Слушаю… говори после сигнала готовности.")
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def listen_loop(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                while self.listening:
                    self.events.put(("status", "Слушаю команду…"))
                    try:
                        audio = recognizer.listen(source, timeout=4, phrase_time_limit=7)
                    except sr.WaitTimeoutError:
                        continue
                    if not self.listening:
                        break
                    self.events.put(("status", "Распознаю речь…"))
                    try:
                        text = recognizer.recognize_google(audio, language="ru-RU")
                    except sr.UnknownValueError:
                        self.events.put(("log", "Не удалось разобрать фразу. Попробуй ещё раз."))
                        continue
                    except sr.RequestError:
                        self.events.put(("log", "Не удалось подключиться к распознаванию речи. Проверь интернет."))
                        self.events.put(("status", "Ошибка распознавания: проверь интернет."))
                        break
                    self.events.put(("heard", text))
                    self.handle_command(text)
        except (OSError, AttributeError) as exc:
            self.events.put(("log", f"Не удалось открыть микрофон: {exc}"))
            self.events.put(("status", "Проверь подключение и разрешения микрофона."))
        except Exception as exc:
            self.events.put(("log", f"Ошибка микрофона: {exc}"))
            self.events.put(("status", "Не удалось запустить микрофон."))
        finally:
            self.listening = False
            self.events.put(("button", "🎙 Слушать"))

    def speak(self, text):
        def worker():
            try:
                with self.engine_lock:
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 178)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
            except Exception as exc:
                self.events.put(("log", f"Голосовой ответ недоступен: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def handle_command(self, spoken):
        command = spoken.lower().strip()
        if command.startswith("робот чай"):
            command = command[len("робот чай"):].strip(" ,.!?")
        self.events.put(("log", f"Ты: {spoken}"))

        if any(phrase in command for phrase in ("останови автоматизацию", "выключи автоматизацию", "останови все режимы")):
            self.stop_automation()
            self.respond("Автоматизация остановлена.")
            return
        if any(word in command for word in ("стоп", "остановись", "хватит слушать")):
            self.listening = False
            self.speak("Хорошо, прекращаю прослушивание.")
            return
        if any(phrase in command for phrase in ("не засыпай", "не дай уснуть", "не переходи в сон", "не выключай компьютер")):
            self.enable_keep_awake()
            return
        if any(phrase in command for phrase in ("двигай мышкой каждую минуту", "двигай мышью каждую минуту", "включи движение мыши", "мышка каждую минуту")):
            self.enable_mouse_nudge()
            return
        if any(phrase in command for phrase in ("выключи защиту от сна", "разреши сон", "можно засыпать")):
            self.disable_keep_awake()
            return
        if any(phrase in command for phrase in ("останови движение мыши", "выключи движение мыши")):
            self.disable_mouse_nudge()
            return
        if "steam" in command or "стим" in command:
            self.launch_app("Steam", [
                os.path.expandvars(r"%ProgramFiles(x86)%\\Steam\\steam.exe"),
                os.path.expandvars(r"%ProgramFiles%\\Steam\\steam.exe"),
            ])
        elif "minecraft" in command or "майнкрафт" in command:
            self.open_minecraft()
        elif "блокнот" in command or "notepad" in command:
            self.launch_command("Блокнот", ["notepad.exe"])
        elif "калькулятор" in command or "калькулятор" in command:
            self.launch_command("Калькулятор", ["calc.exe"])
        elif "браузер" in command or "интернет" in command or "сайт" in command:
            webbrowser.open("https://www.google.com")
            self.respond("Открываю браузер.")
        elif "который час" in command or "время" in command:
            now = datetime.datetime.now().strftime("%H:%M")
            self.respond(f"Сейчас {now}.")
        elif "открой" in command and ("проводник" in command or "файлы" in command):
            self.launch_command("Проводник", ["explorer.exe"])
        elif command.startswith("открой "):
            app_name = command[len("открой "):].strip(" .,!?")
            if app_name:
                self.launch_named_app(app_name)
            else:
                self.respond("Скажи название приложения, например: «открой Discord».")
        elif command in ("привет", "здравствуй", "привет робот чай"):
            self.respond("Привет! Я готов помочь.")
        elif not command:
            self.events.put(("log", "Пустая команда."))
        else:
            self.ask_ai(spoken)


    def configure_ai(self):
        dialog = ctk.CTkInputDialog(
            text="Вставь API-ключ OpenAI. Он сохранится в хранилище учётных данных Windows, а не в GitHub.",
            title="Настройка Robot Tea AI"
        )
        api_key = dialog.get_input()
        if not api_key:
            return
        api_key = api_key.strip()
        if not api_key.startswith("sk-"):
            self.respond("Ключ выглядит необычно. Проверь, что это API-ключ OpenAI.")
            return
        try:
            keyring.set_password("RobotTea", "openai_api_key", api_key)
            self.respond("Ключ сохранён в хранилище учётных данных Windows. Проверю подключение при первом вопросе.")
        except Exception as exc:
            self.events.put(("log", f"Не удалось сохранить ключ в хранилище Windows: {exc}"))
            self.respond("Не удалось безопасно сохранить ключ. Проверь настройки Windows.")

    def send_text_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
        self.message_entry.delete(0, "end")
        self.events.put(("log", f"Ты: {message}"))
        self.ask_ai(message)

    def ask_ai(self, message):
        if self.ai_busy:
            self.events.put(("log", "ИИ ещё готовит ответ. Подожди немного."))
            return
        api_key = keyring.get_password("RobotTea", "openai_api_key")
        if not api_key:
            self.events.put(("status", "Сначала нажми «Настроить ИИ» и добавь API-ключ OpenAI."))
            self.events.put(("log", "ИИ не настроен. Ключ не хранится в репозитории."))
            self.speak("Сначала настрой подключение к искусственному интеллекту.")
            return
        self.ai_busy = True
        self.events.put(("status", "ИИ думает…"))
        threading.Thread(target=self._ask_ai_worker, args=(api_key, message), daemon=True).start()

    def _ask_ai_worker(self, api_key, message):
        try:
            client = OpenAI(api_key=api_key, timeout=45.0, max_retries=1)
            history = self.ai_history[-12:] + [{"role": "user", "content": message}]
            response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=(
                    "Ты — Robot Tea, дружелюбный голосовой помощник для Windows. "
                    "Отвечай по-русски, понятно и кратко. Помогай с вопросами и компьютером, "
                    "но не утверждай, что выполнил действие Windows, если программа его фактически не выполнила. "
                    "Не проси пользователя раскрывать пароли или секретные ключи."
                ),
                input=history,
                max_output_tokens=500,
            )
            answer = (response.output_text or "").strip()
            if not answer:
                answer = "Не получилось сформировать ответ. Попробуй ещё раз."
            self.ai_history.extend([
                {"role": "user", "content": message},
                {"role": "assistant", "content": answer},
            ])
            self.ai_history = self.ai_history[-12:]
            self.events.put(("log", f"Robot Tea AI: {answer}"))
            self.events.put(("status", answer[:180]))
            self.speak(answer)
        except Exception as exc:
            self.events.put(("log", f"Ошибка ИИ: {exc}"))
            self.events.put(("status", "ИИ не ответил. Проверь интернет, API-ключ и доступ к API."))
        finally:
            self.ai_busy = False

    def launch_app(self, label, candidates):
        for path in candidates:
            if path and os.path.isfile(path):
                try:
                    os.startfile(path)
                    self.respond(f"Запускаю {label}.")
                    return
                except OSError:
                    pass
        self.respond(f"{label} не найден. Проверь, установлен ли он.")

    def launch_command(self, label, command):
        try:
            subprocess.Popen(command, shell=False)
            self.respond(f"Открываю: {label}.")
        except OSError as exc:
            self.respond(f"Не удалось открыть {label}.")
            self.events.put(("log", str(exc)))

    def launch_named_app(self, app_name):
        """Launch an installed Windows app by its Start-menu name, without shell command interpolation."""
        aliases = {
            "диспетчер задач": ["taskmgr.exe"],
            "командная строка": ["cmd.exe"],
            "powershell": ["powershell.exe"],
            "терминал": ["wt.exe", "WindowsTerminal.exe"],
            "paint": ["mspaint.exe"],
            "паинт": ["mspaint.exe"],
            "word": ["winword.exe"],
            "ворд": ["winword.exe"],
            "excel": ["excel.exe"],
            "эксель": ["excel.exe"],
            "discord": ["Discord.exe"],
            "дискорд": ["Discord.exe"],
            "telegram": ["Telegram.exe"],
            "телеграм": ["Telegram.exe"],
            "spotify": ["Spotify.exe"],
            "спотифай": ["Spotify.exe"],
            "steam": ["steam.exe"],
            "стим": ["steam.exe"],
        }
        try:
            # First try Windows registered Start-menu apps (including many packaged apps).
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=12, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if completed.returncode == 0 and completed.stdout.strip():
                apps = json.loads(completed.stdout)
                if isinstance(apps, dict):
                    apps = [apps]
                target = app_name.casefold()
                valid = [a for a in apps if isinstance(a, dict) and a.get("Name") and a.get("AppID")]
                exact = [a for a in valid if a["Name"].casefold() == target]
                partial = [a for a in valid if target in a["Name"].casefold()]
                matches = exact or partial
                if matches:
                    chosen = matches[0]
                    os.startfile("shell:AppsFolder\\" + chosen["AppID"])
                    self.respond(f"Открываю {chosen['Name']}.")
                    if len(matches) > 1 and not exact:
                        self.events.put(("log", "Найдено несколько похожих приложений; открыто первое совпадение."))
                    return
        except Exception as exc:
            self.events.put(("log", f"Поиск приложений Windows не удался: {exc}"))

        # Fallback for common classic desktop applications.
        candidates = aliases.get(app_name.casefold(), [app_name])
        for candidate in candidates:
            executable = shutil.which(candidate)
            if executable:
                try:
                    subprocess.Popen([executable], shell=False)
                    self.respond(f"Открываю {app_name}.")
                    return
                except OSError as exc:
                    self.events.put(("log", f"Не удалось запустить {candidate}: {exc}"))
        self.respond(
            f"Не нашёл приложение «{app_name}» в меню Пуск. "
            "Проверь название или попробуй открыть его через меню Пуск Windows."
        )

    def open_minecraft(self):
        # Launcher URIs vary by installation; use the official Minecraft launcher URI.
        try:
            os.startfile("minecraft://")
            self.respond("Пробую открыть Minecraft Launcher.")
        except OSError:
            self.respond("Не удалось открыть Minecraft Launcher. Запусти его один раз вручную.")

    def respond(self, message):
        self.events.put(("log", f"Robot Tea: {message}"))
        self.events.put(("status", message))
        self.speak(message)

    def process_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.write_log(value)
                elif kind == "status":
                    self.set_status(value)
                elif kind == "heard":
                    self.orb.configure(text="◉", text_color="#8bffcf")
                    self.write_log(f"Распознано: {value}")
                elif kind == "button":
                    self.listen_button.configure(text=value)
                    self.orb.configure(text="◉", text_color="#63d7ff")
                elif kind == "awake_button":
                    if value:
                        self.awake_button.configure(text="🌙 Не засыпать: вкл.", fg_color="#176b55")
                    else:
                        self.awake_button.configure(text="🌙 Не засыпать: выкл.", fg_color="#263654")
                elif kind == "mouse_button":
                    if value:
                        self.mouse_button.configure(text="🖱 Двигать мышью: вкл.", fg_color="#176b55")
                    else:
                        self.mouse_button.configure(text="🖱 Двигать мышью: выкл.", fg_color="#263654")
                elif kind == "automation_call":
                    if value == "enable_keep_awake":
                        self.enable_keep_awake()
                    elif value == "disable_keep_awake":
                        self.disable_keep_awake()
                elif kind == "start_mouse_timer":
                    if self.mouse_nudge_active and self.mouse_nudge_job is None:
                        self.mouse_nudge_job = self.after(60000, self._mouse_nudge_tick)
                elif kind == "stop_mouse_timer":
                    if self.mouse_nudge_job is not None:
                        try:
                            self.after_cancel(self.mouse_nudge_job)
                        except Exception:
                            pass
                        self.mouse_nudge_job = None
        except queue.Empty:
            pass
        self.after(100, self.process_events)


if __name__ == "__main__":
    app = RobotTeaApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
